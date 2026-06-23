"""
Stock Price Tracker with Chart
A Flask web application that displays stock prices with interactive charts
"""

import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import plotly
import plotly.graph_objs as go
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Default settings
DEFAULT_SYMBOL = os.getenv('DEFAULT_SYMBOL', 'AAPL')
DEFAULT_PERIOD = '1y'  # 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
DEFAULT_INTERVAL = '1d'  # 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo

def get_stock_data(symbol, period=DEFAULT_PERIOD, interval=DEFAULT_INTERVAL):
    """
    Fetch stock data from Yahoo Finance
    
    Args:
        symbol (str): Stock ticker symbol
        period (str): Time period for data
        interval (str): Data interval
    
    Returns:
        dict: Stock data including price history and metadata
    """
    try:
        # Create ticker object
        ticker = yf.Ticker(symbol)
        
        # Get historical data
        hist = ticker.history(period=period, interval=interval)
        
        # Get current price and other info
        info = ticker.info
        
        # Prepare data for response
        if hist.empty:
            return {'error': 'No data available for this symbol'}
        
        # Get current price
        current_price = hist['Close'].iloc[-1] if not hist.empty else None
        previous_close = info.get('previousClose', None)
        
        # Calculate change
        change = 0
        change_percent = 0
        if previous_close and current_price:
            change = current_price - previous_close
            change_percent = (change / previous_close) * 100
        
        # Prepare historical data for chart
        dates = hist.index.strftime('%Y-%m-%d').tolist()
        prices = hist['Close'].tolist()
        volumes = hist['Volume'].tolist()
        
        # Get moving averages if enough data
        ma_50 = None
        ma_200 = None
        if len(hist) >= 50:
            ma_50 = hist['Close'].rolling(window=50).mean().tolist()
        if len(hist) >= 200:
            ma_200 = hist['Close'].rolling(window=200).mean().tolist()
        
        # Calculate high and low
        high_52w = info.get('fiftyTwoWeekHigh', None)
        low_52w = info.get('fiftyTwoWeekLow', None)
        
        return {
            'symbol': symbol.upper(),
            'name': info.get('longName', symbol.upper()),
            'current_price': round(current_price, 2) if current_price else None,
            'previous_close': round(previous_close, 2) if previous_close else None,
            'change': round(change, 2) if change else None,
            'change_percent': round(change_percent, 2) if change_percent else None,
            'high_52w': round(high_52w, 2) if high_52w else None,
            'low_52w': round(low_52w, 2) if low_52w else None,
            'volume': int(hist['Volume'].iloc[-1]) if not hist.empty else None,
            'avg_volume': info.get('averageVolume', None),
            'market_cap': info.get('marketCap', None),
            'pe_ratio': info.get('trailingPE', None),
            'dividend_yield': info.get('dividendYield', None),
            'dates': dates,
            'prices': prices,
            'volumes': volumes,
            'ma_50': ma_50,
            'ma_200': ma_200,
            'currency': info.get('currency', 'USD')
        }
    except Exception as e:
        return {'error': f'Error fetching data: {str(e)}'}

def create_stock_chart(data):
    """
    Create an interactive Plotly chart from stock data
    
    Args:
        data (dict): Stock data from get_stock_data()
    
    Returns:
        str: JSON string of the Plotly figure
    """
    if 'error' in data:
        return None
    
    # Create figure
    fig = go.Figure()
    
    # Add candlestick chart
    fig.add_trace(go.Candlestick(
        x=data['dates'],
        open=data['prices'],
        high=data['prices'],  # Simplified - using close as high for simplicity
        low=data['prices'],   # Simplified - using close as low for simplicity
        close=data['prices'],
        name='Price',
        increasing_line_color='#26a69a',
        decreasing_line_color='#ef5350',
        line=dict(width=2)
    ))
    
    # Add Moving Averages
    if data.get('ma_50'):
        fig.add_trace(go.Scatter(
            x=data['dates'],
            y=data['ma_50'],
            name='MA 50',
            line=dict(color='#ff9900', width=1.5),
            opacity=0.8
        ))
    
    if data.get('ma_200'):
        fig.add_trace(go.Scatter(
            x=data['dates'],
            y=data['ma_200'],
            name='MA 200',
            line=dict(color='#ff4444', width=1.5),
            opacity=0.8
        ))
    
    # Update layout
    fig.update_layout(
        title=f'{data["symbol"]} - {data["name"]}',
        xaxis_title='Date',
        yaxis_title=f'Price ({data["currency"]})',
        template='plotly_dark',
        height=600,
        hovermode='x unified',
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend=dict(
            x=0.02,
            y=0.98,
            bgcolor='rgba(0,0,0,0.5)',
            bordercolor='rgba(255,255,255,0.2)',
            borderwidth=1
        )
    )
    
    # Add volume as a separate subplot would require more complex layout
    # For simplicity, we'll add volume bars with reduced opacity
    fig.add_trace(go.Bar(
        x=data['dates'],
        y=data['volumes'],
        name='Volume',
        yaxis='y2',
        opacity=0.3,
        marker_color='rgba(100, 149, 237, 0.5)'
    ))
    
    # Create second y-axis for volume
    fig.update_layout(
        yaxis2=dict(
            title='Volume',
            overlaying='y',
            side='right',
            showgrid=False,
            range=[0, max(data['volumes']) * 4] if data['volumes'] else None
        )
    )
    
    # Convert to JSON
    graph_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    return graph_json

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html', default_symbol=DEFAULT_SYMBOL)

@app.route('/api/stock', methods=['GET'])
def get_stock():
    """
    API endpoint to get stock data
    Query params: symbol, period, interval
    """
    symbol = request.args.get('symbol', DEFAULT_SYMBOL)
    period = request.args.get('period', DEFAULT_PERIOD)
    interval = request.args.get('interval', DEFAULT_INTERVAL)
    
    # Validate period
    valid_periods = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max']
    if period not in valid_periods:
        period = DEFAULT_PERIOD
    
    # Validate interval
    valid_intervals = ['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo']
    if interval not in valid_intervals:
        interval = DEFAULT_INTERVAL
    
    # Get data
    data = get_stock_data(symbol, period, interval)
    
    if 'error' in data:
        return jsonify({'error': data['error']}), 404
    
    # Create chart
    chart_json = create_stock_chart(data)
    
    return jsonify({
        'data': data,
        'chart': chart_json
    })

@app.route('/api/search', methods=['GET'])
def search_stocks():
    """
    Search for stocks by symbol or name
    Query param: q (search query)
    """
    query = request.args.get('q', '').strip()
    
    if not query:
        return jsonify({'results': []})
    
    try:
        # Search using yfinance
        ticker = yf.Ticker(query.upper())
        info = ticker.info
        
        if info and 'symbol' in info:
            results = [{
                'symbol': info.get('symbol', ''),
                'name': info.get('longName', info.get('shortName', '')),
                'exchange': info.get('exchange', '')
            }]
        else:
            results = []
        
        return jsonify({'results': results})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
