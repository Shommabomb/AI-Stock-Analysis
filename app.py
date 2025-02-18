print("Hello Papa!")

# Libraries
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import tempfile
import os
import json
from datetime import datetime, timedelta
from openai import OpenAI

# Configure the API key - IMPORTANT: Use Streamlit secrets or environment variables for security
# For now, using hardcoded API key - REPLACE WITH YOUR ACTUAL API KEY SECURELY
DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# Set up Streamlit app
st.set_page_config(layout="wide")
st.title("AI-Powered Technical Stock Analysis Dashboard")
st.sidebar.header("Configuration")

# Input for multiple stock tickers (comma-separated)
tickers_input = st.sidebar.text_input("Enter Stock Tickers (comma-separated):", "AAPL,MSFT,GOOG")
# Parse tickers by stripping extra whitespace and splitting on commas
tickers = [ticker.strip().upper() for ticker in tickers_input.split(",") if ticker.strip()]

# Set the date range: start date = one year before today, end date = today
end_date_default = datetime.today()
start_date_default = end_date_default - timedelta(days=365)
start_date = st.sidebar.date_input("Start Date", value=start_date_default)
end_date = st.sidebar.date_input("End Date", value=end_date_default)

# Technical indicators selection (applied to every ticker)
st.sidebar.subheader("Technical Indicators")
indicators = st.sidebar.multiselect(
    "Select Indicators:",
    ["20-Day SMA", "20-Day EMA", "20-Day Bollinger Bands", "VWAP"],
    default=["20-Day SMA"]
)

# Button to fetch data for all tickers
if st.sidebar.button("Fetch Data"):
    stock_data = {}
    for ticker in tickers:
        # Download data for each ticker using yfinance
        data = yf.download(ticker, start=start_date, end=end_date)
        if not data.empty:
            stock_data[ticker] = data
        else:
            st.warning(f"No data found for {ticker}.")
    st.session_state["stock_data"] = stock_data
    st.success("Stock data loaded successfully for: " + ", ".join(stock_data.keys()))

# Ensure we have data to analyze
if "stock_data" in st.session_state and st.session_state["stock_data"]:

    # Define a function to build chart, call the Deepseek API and return structured result
    def analyze_ticker(ticker, data):
        # Build candlestick chart for the given ticker's data
        fig = go.Figure(data=[
            go.Candlestick(
                x=data.index,
                open=data['Open'],
                high=data['High'],
                low=data['Low'],
                close=data['Close'],
                name="Candlestick"
            )
        ])

        # Add selected technical indicators
        def add_indicator(indicator):
            if indicator == "20-Day SMA":
                sma = data['Close'].rolling(window=20).mean()
                fig.add_trace(go.Scatter(x=data.index, y=sma, mode='lines', name='SMA (20)'))
            elif indicator == "20-Day EMA":
                ema = data['Close'].ewm(span=20).mean()
                fig.add_trace(go.Scatter(x=data.index, y=ema, mode='lines', name='EMA (20)'))
            elif indicator == "20-Day Bollinger Bands":
                sma = data['Close'].rolling(window=20).mean()
                std = data['Close'].rolling(window=20).std()
                bb_upper = sma + 2 * std
                bb_lower = sma - 2 * std
                fig.add_trace(go.Scatter(x=data.index, y=bb_upper, mode='lines', name='BB Upper'))
                fig.add_trace(go.Scatter(x=data.index, y=bb_lower, mode='lines', name='BB Lower'))
            elif indicator == "VWAP":
                data['VWAP'] = (data['Close'] * data['Volume']).cumsum() / data['Volume'].cumsum()
                fig.add_trace(go.Scatter(x=data.index, y=data['VWAP'], mode='lines', name='VWAP'))
        for ind in indicators:
            add_indicator(ind)
        fig.update_layout(xaxis_rangeslider_visible=False)

        # Save chart as temporary PNG file and read image bytes
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmpfile:
            fig.write_image(tmpfile.name)
            tmpfile_path = tmpfile.name
        with open(tmpfile_path, "rb") as f:
            image_bytes = f.read()
        os.remove(tmpfile_path)

        # Updated prompt asking for a detailed justification of technical analysis and a recommendation.
        analysis_prompt = (
            f"Act as a financial analyst specializing in technical analysis of stocks, ETFs, and cryptocurrencies. your expertise includes asset trends, momentum, volatility, and volume assessments. you employ various strategies such as screening high-quality stocks, evaluating trend, idiosyncratic, and risk-adjusted momentum, and identifying top sectors. When requested to build a portfolio, you now ask whether to base it on Risk Adjusted Momentum, Idiosyncratic Momentum, Trend Momentum, or the Quality Approach. This ensures a tailored analysis and portfolio creation based on the user's specific needs. You present data in a structured table format with headings tailored for comprehensive stock or sector analysis. You use real-time internet sources to ensure accuracy and relevance in your analysis. When the user types in a ticker, you show the options for technical analysis, fundamental analysis, or an investment report. The investment report includes an in-depth analysis of the company’s financial performance, growth proscts, and investment potential, formatted to include a summary, core metrics, financial performance, growth prospects, recent news, upgrades and downgrades, and a final recommendation, with a chart included. All reports include current data from real-time internet sources. The technical analysis is formatted to include an overview, analysis of trend indicators, momentum indicators, volatility indicators, volume indicators, key observations, and a conclusion. Note: Your insights are not financial advice and should be used for informational purposes only. Users should perform their own due diligence before making investment decisions. Use the following rules to screen CANSLIM stocks - Screener Rules. Get current stock price and news for any stock that is being talked about or when a ticker is entered in chat. Check current news, volume and historical price data for a stock and analyse the current news and then explain if the stock price is under or overvalued based on the stock closing price for last five years based on daily volumes, price, company fundamentals and news and explain what it would expect to happen to price over the next few weeks considering the articles  and price/volume data over the last three years. Also consider relative strength of the stock, macro environment and economic news.In the technical analysis,  include RSI, EMA and ADX analysis from yfinance. In your technical analysis include Mark Minervini's VCP strategy, SL and entry points and stage analysis by stan weinstein."
            f"Analyze the stock chart for {ticker} based on its candlestick chart and the displayed technical indicators. "
            f"Provide a detailed justification of your analysis, explaining what patterns, signals, and trends you observe. "
            f"Then, based solely on the chart, provide a recommendation from the following options: "
            f"'Strong Buy', 'Buy', 'Weak Buy', 'Hold', 'Weak Sell', 'Sell', or 'Strong Sell'. "
            f"Return your output as a JSON object with two keys: 'action' and 'justification'."
        )

        # Call the Deepseek API
        response = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[
                {"role": "system", "content": analysis_prompt},
                {"role": "user", "content": analysis_prompt}
            ],
            stream=False
        )

        try:
            # Attempt to parse JSON from the response text
            result_text = response.choices[0].message.content
            # Find the start and end of the JSON object within the text (if Deepseek includes extra text)
            json_start_index = result_text.find('{')
            json_end_index = result_text.rfind('}') + 1  # +1 to include the closing brace
            if json_start_index != -1 and json_end_index > json_start_index:
                json_string = result_text[json_start_index:json_end_index]
                result = json.loads(json_string)
            else:
                raise ValueError("No valid JSON object found in the response")

        except json.JSONDecodeError as e:
            result = {"action": "Error", "justification": f"JSON Parsing error: {e}. Raw response text: {result_text}"}
        except ValueError as ve:
            result = {"action": "Error", "justification": f"Value Error: {ve}. Raw response text: {result_text}"}
        except Exception as e:
            result = {"action": "Error", "justification": f"General Error: {e}. Raw response text: {result_text}"}

        return fig, result

    # Create tabs: first tab for overall summary, subsequent tabs per ticker
    tab_names = ["Overall Summary"] + list(st.session_state["stock_data"].keys())
    tabs = st.tabs(tab_names)

    # List to store overall results
    overall_results = []

    # Process each ticker and populate results
    for i, ticker in enumerate(st.session_state["stock_data"]):
        data = st.session_state["stock_data"][ticker]
        # Analyze ticker: get chart figure and structured output result
        fig, result = analyze_ticker(ticker, data)
        overall_results.append({"Stock": ticker, "Recommendation": result.get("action", "N/A")})
        # In each ticker-specific tab, display the chart and detailed justification
        with tabs[i + 1]:
            st.subheader(f"Analysis for {ticker}")
            st.plotly_chart(fig)
            st.write("**Detailed Justification:**")
            st.write(result.get("justification", "No justification provided."))

    # In the Overall Summary tab, display a table of all results
    with tabs[0]:
        st.subheader("Overall Structured Recommendations")
        df_summary = pd.DataFrame(overall_results)
        st.table(df_summary)
else:
    st.info("Please fetch stock data using the sidebar.")