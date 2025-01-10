# -*- coding: utf-8 -*-
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from binance.client import Client
import pandas as pd
import time
import logging
import os

# Configuração inicial
API_KEY = ''  # Substitua pela sua chave da API Binance
API_SECRET = ''  # Substitua pelo seu segredo da API Binance
client = Client(API_KEY, API_SECRET)  # Instanciando o cliente Binance com as chaves fornecidas

# Configuração de e-mail
EMAIL_REMETENTE = ""
EMAIL_SENHA = ""
EMAIL_DESTINATARIO = ""

# Parâmetros do usuário
CAPITAL_DISPONIVEL = 15  # Capital disponível para comprar
STOP_LOSS_PERCENT = 0.02  # Stop Loss em 2%
TAKE_PROFIT_PERCENT = 0.05  # Take Profit em 5%
PERIODO = '1h'  # Período de análise
USAR_PARES_AUTOMATICOS = False

# Definir pares manualmente ou automático
if USAR_PARES_AUTOMATICOS:
    tickers = client.get_ticker()
    PARES = [t['symbol'] for t in tickers if t['symbol'].endswith('USDT')][:20]
else:
    PARES = [
        'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ADAUSDT', 'XRPUSDT',
        'DOGEUSDT', 'DOTUSDT', 'LTCUSDT', 'SHIBUSDT',
        'AVAXUSDT', 'LINKUSDT'
    ]

log_dir = r'C:\VSCode\Bot'
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'BotBinanceDados.log')
logging.basicConfig(
    filename=log_file,
    level=logging.DEBUG,
    format='%(asctime)s %(message)s'
)

def enviar_email(assunto, mensagem):
    """
    Envia um e-mail de notificação.
    """
    try:
        # Configuração do e-mail
        email = MIMEMultipart()
        email["From"] = EMAIL_REMETENTE
        email["To"] = EMAIL_DESTINATARIO
        email["Subject"] = assunto
        email.attach(MIMEText(mensagem, "plain"))

        # Enviar e-mail
        with smtplib.SMTP("smtp.gmail.com", 587) as servidor:
            servidor.starttls()
            servidor.login(EMAIL_REMETENTE, EMAIL_SENHA)
            servidor.sendmail(EMAIL_REMETENTE, EMAIL_DESTINATARIO, email.as_string())
            logging.info("E-mail enviado com sucesso.")
    except Exception as e:
        logging.error(f"Erro ao enviar e-mail: {e}", exc_info=True)

def obter_precisao(symbol):
    """
    Obtém a precisão da quantidade permitida para um símbolo (par de negociação).
    """
    info = client.get_symbol_info(symbol)
    for filt in info['filters']:
        if filt['filterType'] == 'LOT_SIZE':
            return int(filt['stepSize'].find('1') - 1)  # Retorna a quantidade de casas decimais permitidas
    return 0  # Se não encontrar a precisão, retorna 0

def get_data(symbol, interval, limit=300):
    try:
        candles = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        if not candles:
            logging.error(f"Nenhum dado retornado para {symbol}.")
            return None
        df = pd.DataFrame(candles, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
        ])
        df['close'] = pd.to_numeric(df['close'])
        df['open'] = pd.to_numeric(df['open'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['volume'] = pd.to_numeric(df['volume'])
        return df
    except Exception as e:
        logging.error(f"Erro ao obter dados para {symbol}: {e}", exc_info=True)
        return None

def medias_moveis(data):
    data['sma_50'] = data['close'].rolling(window=50).mean()
    data['sma_200'] = data['close'].rolling(window=200).mean()
    print(f"SMA 50: {data['sma_50'].iloc[-1]}, SMA 200: {data['sma_200'].iloc[-1]}")
    
    if data['sma_50'].iloc[-1] > data['sma_200'].iloc[-1]:
        return "compra"
    elif data['sma_50'].iloc[-1] < data['sma_200'].iloc[-1]:
        return "venda"
    return "manter"

def rsi(data, period=14):
    delta = data['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    data['rsi'] = 100 - (100 / (1 + rs))
    print(f"RSI: {data['rsi'].iloc[-1]}")
    
    if data['rsi'].iloc[-1] < 30:
        return "compra"
    elif data['rsi'].iloc[-1] > 70:
        return "venda"
    return "manter"

def executar_analises(data):
    sinais = []
    sinal_mm = medias_moveis(data)
    sinal_rsi = rsi(data)
    
    print(f"Sinal de Média Móvel: {sinal_mm}, Sinal de RSI: {sinal_rsi}")
    
    if sinal_mm == "compra" and sinal_rsi == "compra":
        sinais.append("compra")
    elif sinal_mm == "venda" and sinal_rsi == "venda":
        sinais.append("venda")
    else:
        sinais.append("manter")
    
    logging.debug(f"Sinais gerados: {sinais}")
    return sinais

def executar_acao(symbol, sinal):
    """
    Modificado para enviar notificações por e-mail após cada compra ou venda.
    """
    try:
        preco_atual = float(client.get_symbol_ticker(symbol=symbol)['price'])
        balance = float(client.get_asset_balance(asset='USDT')['free'])
        logging.debug(f"Saldo de USDT: {balance}, Preço atual de {symbol}: {preco_atual}")

        if sinal == "compra":
            if balance >= 15:  # Certifique-se de que há saldo suficiente para comprar
                precisao = obter_precisao(symbol)
                qty = round(CAPITAL_DISPONIVEL / preco_atual, precisao)
                if qty > 0:
                    ordem = client.order_market_buy(symbol=symbol, quantity=qty)
                    logging.info(f"Compra executada para {symbol}, quantidade: {qty}, detalhes: {ordem}")
                    enviar_email(
                        f"Compra realizada: {symbol}",
                        f"Uma compra foi realizada para {symbol}.\nQuantidade: {qty}\nPreço: {preco_atual}"
                    )
                    return ordem
                else:
                    logging.warning(f"Quantidade calculada inválida para {symbol}.")
            else:
                logging.warning(f"Saldo insuficiente para compra de {symbol}.")

        elif sinal == "venda":
            balance_symbol = float(client.get_asset_balance(asset=symbol[:-4])['free'])
            if balance_symbol > 0:
                ordem = client.order_market_sell(symbol=symbol, quantity=balance_symbol)
                logging.info(f"Venda executada para {symbol}, quantidade: {balance_symbol}")
                enviar_email(
                    f"Venda realizada: {symbol}",
                    f"Uma venda foi realizada para {symbol}.\nQuantidade: {balance_symbol}\nPreço: {preco_atual}"
                )
                return ordem
            else:
                logging.warning(f"Saldo insuficiente de {symbol[:-4]} para venda.")
    except Exception as e:
        logging.error(f"Erro ao executar ação para {symbol}: {e}", exc_info=True)
        return None

def monitorar_ordem(ordem, symbol):
    try:
        preco_inicial = float(ordem['fills'][0]['price'])
        stop_loss = preco_inicial * (1 - STOP_LOSS_PERCENT)
        take_profit = preco_inicial * (1 + TAKE_PROFIT_PERCENT)

        logging.debug(f"Monitorando ordem de {symbol}. Stop Loss: {stop_loss}, Take Profit: {take_profit}")

        # Loop para monitorar preço
        while True:
            preco_atual = float(client.get_symbol_ticker(symbol=symbol)['price'])
            logging.debug(f"Preço atual de {symbol}: {preco_atual}")

            if preco_atual <= stop_loss:
                logging.debug(f"Stop-loss acionado para {symbol} no preço {preco_atual}")
                executar_acao(symbol, "venda")
                break
            elif preco_atual >= take_profit:
                logging.debug(f"Take-profit acionado para {symbol} no preço {preco_atual}")
                executar_acao(symbol, "venda")
                break
            
            # Aguardar um pouco antes de verificar novamente
            time.sleep(180)  # 03 Minutos é um bom intervalo para reduzir chamadas excessivas
    except Exception as e:
        logging.error(f"Erro ao monitorar ordem para {symbol}: {e}", exc_info=True)

# Loop principal
try:
    while True:
        for pair in PARES:
            print(f"Analisando {pair}...")
            data = get_data(pair, PERIODO)
            if data is None or data.empty:
                logging.error(f"Pulando {pair} devido à falta de dados.")
                continue
            sinais = executar_analises(data)
            
            if "compra" in sinais:
                ordem = executar_acao(pair, "compra")
                if ordem:
                    logging.info(f"Compra realizada com sucesso para {pair}")
                    monitorar_ordem(ordem, pair)  # Monitorar a ordem após a compra
            elif "venda" in sinais:
                ordem = executar_acao(pair, "venda")
                if ordem:
                    logging.info(f"Venda realizada com sucesso para {pair}")
            else:
                logging.debug(f"Nenhuma ação para {pair}.")
        
        print("Aguardando próximo ciclo...")
        time.sleep(60 * 3)  # Aguardar 3 minutos antes de executar a próxima análise
except Exception as e:
    logging.error(f"Erro no loop principal: {e}", exc_info=True)
    print(f"Erro: {e}")
