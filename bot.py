import telebot
import schedule
import time
import threading
import requests
import re # <-- Nueva librería para buscar patrones en textos
from flask import Flask
import os

# Leemos las claves del servidor (variables de entorno)
TOKEN = os.environ.get('TELEGRAM_TOKEN')
BIN_ID = os.environ.get('BIN_ID')
API_KEY = os.environ.get('JSONBIN_KEY')

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

def cargar_datos():
    url = f"https://api.jsonbin.io/v3/b/{BIN_ID}/latest"
    headers = {"X-Master-Key": API_KEY}
    try:
        return requests.get(url, headers=headers).json().get('record', {})
    except:
        return {}

def guardar_datos(datos):
    url = f"https://api.jsonbin.io/v3/b/{BIN_ID}"
    headers = {"Content-Type": "application/json", "X-Master-Key": API_KEY}
    requests.put(url, json=datos, headers=headers)

# --- COMANDOS DE TELEGRAM ---

@bot.message_handler(commands=['start'])
def bienvenida(message):
    bot.reply_to(message, "¡Hola! Registra tu ticket así: /ticket 482")

@bot.message_handler(commands=['ticket'])
def registrar_ticket(message):
    try:
        numero = message.text.split()[1]
        if len(numero) == 3 and numero.isdigit():
            datos = cargar_datos()
            datos[str(message.chat.id)] = numero
            guardar_datos(datos)
            bot.reply_to(message, f"✅ Ticket {numero} guardado. Te aviso a las 22:00.")
        else:
            bot.reply_to(message, "⚠️ Formato incorrecto. Ejemplo: /ticket 482")
    except:
        bot.reply_to(message, "⚠️ Falta el número.")

@bot.message_handler(commands=['test'])
def forzar_comprobacion(message):
    bot.reply_to(message, "🔍 Comprobando sorteo en la web oficial de la ONCE...")
    comprobar_premio()

# --- LÓGICA DEL SORTEO (ACTUALIZADA Y BLINDADA) ---

def obtener_numero_once():
    # Extraemos el número directamente de la web oficial de la ONCE
    url = "https://www.juegosonce.es/resultados-cupon-diario"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        html = requests.get(url, headers=headers).text
        # Busca la palabra "Número" o "premiado", salta los caracteres extraños y atrapa los primeros 5 dígitos que encuentre
        match = re.search(r'(?:N[úu]mero|premiado)[^\d]*(\d{5})', html, re.IGNORECASE)
        if match:
            return match.group(1)
        return None
    except:
        return None

def comprobar_premio():
    numero_ganador = obtener_numero_once()
    
    # ESCUDO DE SEGURIDAD: Comprobamos que el número exista y sean estrictamente 5 dígitos
    if not numero_ganador or not numero_ganador.isdigit() or len(numero_ganador) != 5:
        datos = cargar_datos()
        for chat_id in datos.keys():
            bot.send_message(chat_id, "⚠️ No he podido verificar el número de la ONCE. Es posible que los resultados aún no estén publicados o la web falle.")
        return

    datos = cargar_datos()
    for chat_id, ticket in datos.items():
        # Comparamos tu ticket con los últimos 3 dígitos de la ONCE
        if ticket == numero_ganador[-3:]:
            bot.send_message(chat_id, f"¡BINGO! 🎉 ONCE: {numero_ganador}. ¡Tus dígitos ({ticket}) coinciden! 50€ al bolsillo.")
        else:
            bot.send_message(chat_id, f"Hoy no hubo suerte. ONCE: {numero_ganador}, tu ticket: {ticket}.")
            
    # Vaciamos para el día siguiente
    guardar_datos({}) 

# ------------------------------------------------

def tareas_programadas():
    schedule.every().day.at("22:00").do(comprobar_premio)
    while True:
        schedule.run_pending()
        time.sleep(1)

def iniciar_bot():
    bot.polling(none_stop=True)

@app.route('/')
def home():
    return "¡Bot funcionando!"

if __name__ == '__main__':
    threading.Thread(target=iniciar_bot, daemon=True).start()
    threading.Thread(target=tareas_programadas, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)