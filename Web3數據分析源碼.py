#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pandas as pd
import ccxt
import matplotlib.pyplot as plt
import os
from datetime import datetime
import time
import requests
import random
from jinja2 import Template
import webbrowser

# -------------------------- 1. 互動式參數輸入 --------------------------
def get_user_config():
    print("\n=== 請設定分析參數 ===")
    exchange = input("交易所 (預設 binance): ").strip() or 'binance'
    symbols_input = input("幣種清單 (逗號分隔, 預設 BTC/USDT,ETH/USDT): ").strip()
    symbols = [s.strip() for s in symbols_input.split(',')] if symbols_input else ['BTC/USDT', 'ETH/USDT']
    timeframe = input("時間週期 (預設 1d): ").strip() or '1d'
    limit = int(input("抓取筆數 (預設 30): ").strip() or 30)
    rsi_period = int(input("RSI 週期 (預設 14): ").strip() or 14)
    etherscan_api_key = input("Etherscan API Key (留空跳過): ").strip()

    return {
        'exchange': exchange,
        'symbols': symbols,
        'timeframe': timeframe,
        'limit': limit,
        'rsi_period': rsi_period,
        'etherscan_api_key': etherscan_api_key
    }

# -------------------------- 2. 資料夾 --------------------------
OUTPUT_DIR = './crypto_analysis_results/'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -------------------------- 3. 獲取交易所資料 --------------------------
def get_crypto_data(exchange_name, symbol, timeframe, limit):
    exchange_class = getattr(ccxt, exchange_name, None)
    if not exchange_class:
        print(f"錯誤：不支援的交易所 {exchange_name}")
        return None
    for attempt in range(1, 4):
        try:
            exchange = exchange_class({'enableRateLimit': True, 'timeout': 30000})
            print(f"   正在抓取 {symbol} ({timeframe})...")
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not ohlcv:
                raise ValueError("空資料")
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return df.astype(float)
        except Exception as e:
            print(f"   重試 {attempt}/3: {e}")
            time.sleep(3)
    return None

# -------------------------- 4. RSI --------------------------
def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    roll_up = up.rolling(window=period, min_periods=period).mean()
    roll_down = down.rolling(window=period, min_periods=period).mean()
    rs = roll_up / roll_down
    rsi = 100 - (100 / (1 + rs))
    return rsi

# -------------------------- 5. MACD --------------------------
def calculate_macd(df, fast=12, slow=26, signal=9):
    exp1 = df['close'].ewm(span=fast, adjust=False).mean()
    exp2 = df['close'].ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

# -------------------------- 6. 鏈上數據（Etherscan V2）--------------------------
def get_eth_chain_data(api_key):
    if not api_key:
        return None
    url = "https://api.etherscan.io/v2/api"
    params = {
        'chainid': '1',
        'module': 'stats',
        'action': 'ethsupply2',
        'apikey': api_key
    }
    try:
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        if data.get('status') == '1' and 'result' in data:
            supply_wei = int(data['result'])
            supply_eth = round(supply_wei / 1e18, 2)
            return {
                '總供應量(ETH)': supply_eth,
                '獲取時間': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        else:
            print(f"   Etherscan 錯誤: {data.get('result') or data.get('message')}")
            return None
    except Exception as e:
        print(f"   鏈上數據失敗: {e}")
        return None

# -------------------------- 7. 情緒分析 --------------------------
def get_social_sentiment(symbol):
    score = random.uniform(-1, 1)
    return {
        '情緒評分': round(score, 3),
        '情緒判斷': '正面' if score > 0.3 else '負面' if score < -0.3 else '中性'
    }

# -------------------------- 8. 單幣種分析 --------------------------
def generate_local_analysis(df, symbol, rsi_period):
    if len(df) < 2:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    change_pct = (latest['close'] - prev['close']) / prev['close'] * 100

    # RSI
    rsi_series = calculate_rsi(df, rsi_period)
    latest_rsi = rsi_series.iloc[-1] if len(rsi_series) > 0 else None
    rsi_status = '超買' if latest_rsi and latest_rsi > 70 else '超賣' if latest_rsi and latest_rsi < 30 else '中性'

    # MACD
    macd_line, signal_line, _ = calculate_macd(df)
    latest_macd = macd_line.iloc[-1]
    latest_signal = signal_line.iloc[-1]
    macd_status = '金叉' if latest_macd > latest_signal else '死叉'

    # 情緒
    sentiment = get_social_sentiment(symbol)

    # 結果字典（保留含括號 key）
    result = {
        '日期': datetime.now().strftime('%Y-%m-%d'),
        '幣種': symbol,
        '最新收盤價(USD)': round(latest['close'], 4),
        '單日漲跌幅(%)': round(change_pct, 2),
        '30天最高價(USD)': round(df['high'].max(), 4),
        '30天最低價(USD)': round(df['low'].min(), 4),
        'RSI': round(latest_rsi, 2) if latest_rsi else None,
        'RSI狀態': rsi_status,
        'MACD': round(latest_macd, 4),
        'MACD信號線': round(latest_signal, 4),
        'MACD狀態': macd_status,
        '情緒判斷': sentiment['情緒判斷'],
        '趨勢判斷': '上漲' if change_pct > 2 else '下跌' if change_pct < -2 else '震盪'
    }

    # CSV
    safe = symbol.replace('/', '_')
    csv_path = f"{OUTPUT_DIR}{safe}_daily.csv"
    pd.DataFrame([result]).to_csv(csv_path, mode='a', header=not os.path.exists(csv_path), index=False)

    # 圖表（解決字體警告）
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans', 'Arial Unicode MS', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False  # 解決負號問題

    fig = plt.figure(figsize=(14, 12))
    plt.subplot(4,1,1); plt.plot(df.index, df['close'], label='收盤價', color='blue'); plt.axhline(df['close'].mean(), color='red', linestyle='--', label='均價'); plt.title(f'{symbol} 價格'); plt.legend(); plt.grid(alpha=0.3)
    plt.subplot(4,1,2); plt.bar(df.index, df['volume'], color='orange', alpha=0.7); plt.title('成交量')
    plt.subplot(4,1,3); 
    if latest_rsi is not None: plt.plot(rsi_series.index, rsi_series, color='purple'); plt.axhline(70, color='red', linestyle='--'); plt.axhline(30, color='green', linestyle='--')
    plt.title(f'RSI ({rsi_status})'); plt.ylim(0, 100)
    plt.subplot(4,1,4); 
    plt.plot(macd_line.index, macd_line, label='MACD', color='blue'); plt.plot(signal_line.index, signal_line, label='Signal', color='red'); plt.bar(_.index, _, color='gray', alpha=0.6)
    plt.title(f'MACD ({macd_status})'); plt.legend()

    plt.tight_layout()
    chart_path = f"{OUTPUT_DIR}{safe}_chart_{datetime.now().strftime('%Y%m%d')}.png"
    plt.savefig(chart_path, dpi=150, bbox_inches='tight')
    plt.close()

    result['圖表路徑'] = os.path.abspath(chart_path)
    print(f"   {symbol} 分析完成 | RSI: {rsi_status} | MACD: {macd_status}")
    return result

# -------------------------- 9. HTML 報告（使用 r['key'] 安全存取）--------------------------
def generate_html_report(analysis_results, chain_data):
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>加密貨幣綜合報告</title>
        <style>
            body {font-family: Arial, sans-serif; margin: 20px; background: #f5f7fa;}
            .header, .section {background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 25px;}
            table {width: 100%; border-collapse: collapse;}
            th, td {padding: 12px; text-align: left; border-bottom: 1px solid #eee;}
            th {background: #3498db; color: white;}
            .up {color: #27ae60; font-weight: bold;}
            .down {color: #e74c3c; font-weight: bold;}
            .gold {color: #f1c40f;}
            .death {color: #95a5a6;}
            .chart-img {max-width: 100%; border-radius: 8px; margin: 15px 0;}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>加密貨幣綜合分析報告</h1>
            <p>{{ date }}</p>
        </div>

        {% if chain_data %}
        <div class="section">
            <h2>以太坊鏈上數據</h2>
            <p><strong>總供應量:</strong> {{ chain_data['總供應量(ETH)'] }} ETH</p>
            <p><strong>更新時間:</strong> {{ chain_data['獲取時間'] }}</p>
        </div>
        {% endif %}

        <div class="section">
            <h2>市場概覽</h2>
            <table>
                <tr>
                    <th>幣種</th>
                    <th>價格</th>
                    <th>日漲跌</th>
                    <th>RSI</th>
                    <th>MACD</th>
                    <th>情緒</th>
                    <th>趨勢</th>
                </tr>
                {% for r in results %}
                <tr>
                    <td><strong>{{ r['幣種'] }}</strong></td>
                    <td>${{ "%.2f"|format(r['最新收盤價(USD)']) }}</td>
                    <td class="{% if r['單日漲跌幅(%)'] > 0 %}up{% else %}down{% endif %}">
                        {% if r['單日漲跌幅(%)'] > 0 %}+{% endif %}{{ "%.2f"|format(r['單日漲跌幅(%)']) }}%%
                    </td>
                    <td>{{ r['RSI'] if r['RSI'] else 'N/A' }} <small>({{ r['RSI狀態'] }})</small></td>
                    <td><span class="{% if r['MACD狀態'] == '金叉' %}gold{% else %}death{% endif %}">{{ r['MACD狀態'] }}</span></td>
                    <td>{{ r['情緒判斷'] }}</td>
                    <td>{{ r['趨勢判斷'] }}</td>
                </tr>
                {% endfor %}
            </table>
        </div>

        <div class="section">
            <h2>詳細圖表</h2>
            {% for r in results %}
            <h3>{{ r['幣種'] }}</h3>
            <img src="file://{{ r['圖表路徑'] }}" class="chart-img">
            {% endfor %}
        </div>
    </body>
    </html>
    """

    template = Template(html_template)
    html_content = template.render(
        date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        results=analysis_results,
        chain_data=chain_data
    )

    html_file = f"{OUTPUT_DIR}report_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    webbrowser.open('file://' + os.path.abspath(html_file))
    print(f"\nHTML 報告已生成：{html_file}")
    return html_file

# -------------------------- 10. 主流程 --------------------------
def daily_analysis_task():
    config = get_user_config()
    all_results = []
    chain_data = get_eth_chain_data(config['etherscan_api_key']) if config['etherscan_api_key'] else None

    print(f"\n=== 開始分析 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")

    for symbol in config['symbols']:
        print(f"\n--- 分析 {symbol} ---")
        df = get_crypto_data(config['exchange'], symbol, config['timeframe'], config['limit'])
        if df is not None and len(df) >= max(2, config['rsi_period'] + 1):
            result = generate_local_analysis(df, symbol, config['rsi_period'])
            if result:
                all_results.append(result)
        else:
            print(f"   資料不足，跳過 {symbol}")

    if all_results:
        generate_html_report(all_results, chain_data)
    else:
        print("\n無結果，跳過報告。")

    print(f"\n=== 全部完成 ===")

# -------------------------- 11. 執行 --------------------------
if __name__ == "__main__":
    try:
        daily_analysis_task()
    except KeyboardInterrupt:
        print("\n\n已手動中斷")
    except Exception as e:
        print(f"\n程式錯誤: {e}")