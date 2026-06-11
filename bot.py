import telebot
import schedule
import time
import threading
import requests
import re
from flask import Flask
import os

# Leemos las claves del servidor (variables de entorno)
TOKEN = os.environ.get('TELEGRAM_TOKEN')
BIN_ID = os.environ.get('BIN_ID')
API_KEY = os.environ.get('JSONBIN_KEY')

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- GESTIÓN DE BASE DE DATOS ---
def cargar_datos():
    url = f"https://api.jsonbin.io/v3/b/{BIN_ID}/latest"
    headers = {"X-Master-Key": API_KEY}
    try:
        res = requests.get(url, headers=headers).json().get('record', {})
        if "tickets" not in res or "stats" not in res:
            return {"tickets": {}, "stats": {}}
        return res
    except:
        return {"tickets": {}, "stats": {}}

def guardar_datos(datos):
    url = f"https://api.jsonbin.io/v3/b/{BIN_ID}"
    headers = {"Content-Type": "application/json", "X-Master-Key": API_KEY}
    requests.put(url, json=datos, headers=headers)

# --- COMANDOS DE TELEGRAM ---
@bot.message_handler(commands=['start'])
def bienvenida(message):
    bot.reply_to(message, "¡Hola! Gestiona tu ticket del parking con estos comandos:\n\n"
                          "🔹 `/ticket 482` - Registra tu número para hoy.\n"
                          "🔹 `/ver` - Comprueba el número que tienes guardado hoy.\n"
                          "🔹 `/stats` - Mira tu historial de juego.")

@bot.message_handler(commands=['ticket'])
def registrar_ticket(message):
    try:
        numero = message.text.split()[1]
        if len(numero) == 3 and numero.isdigit():
            datos = cargar_datos()
            chat_id = str(message.chat.id)
            datos["tickets"][chat_id] = numero
            if chat_id not in datos["stats"]:
                datos["stats"][chat_id] = {"jugados": 0, "ganados": 0}
            guardar_datos(datos)
            bot.reply_to(message, f"✅ Ticket {numero} guardado. Te aviso a las 22:00.")
        else:
            bot.reply_to(message, "⚠️ Formato incorrecto. Ejemplo: /ticket 482")
    except:
        bot.reply_to(message, "⚠️ Falta el número.")

@bot.message_handler(commands=['ver'])
def ver_ticket(message):
    datos = cargar_datos()
    chat_id = str(message.chat.id)
    ticket = datos["tickets"].get(chat_id)
    if ticket:
        bot.reply_to(message, f"🎫 Para el sorteo de hoy tienes guardado el número: *{ticket}*", parse_mode="Markdown")
    else:
        bot.reply_to(message, "🔍 Aún no has registrado ningún ticket para hoy. Usa /ticket seguido de tus 3 números.")

@bot.message_handler(commands=['stats'])
def ver_estadisticas(message):
    datos = cargar_datos()
    chat_id = str(message.chat.id)
    user_stats = datos["stats"].get(chat_id, {"jugados": 0, "ganados": 0})
    bot.reply_to(message, f"📊 *Tus Estadísticas del Parking:*\n\n"
                          f"🔹 Sorteos jugados: {user_stats['jugados']}\n"
                          f"🏆 Premios ganados: {user_stats['ganados']}", parse_mode="Markdown")

@bot.message_handler(commands=['test'])
def forzar_comprobacion(message):
    bot.reply_to(message, "🔍 Comprobando sorteo en la web oficial de la ONCE...")
    comprobar_premio()

# --- LÓGICA DEL SORTEO Y ALERTAS (CON FILTRO DE IMPUREZAS HTML) ---
def obtener_numero_once():
    url = "https://www.juegosonce.es/resultados-cupon-diario"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        html = requests.get(url, headers=headers).text
        
        # 1. Limpiamos TODAS las etiquetas HTML para dejar solo el texto
        texto_limpio = re.sub(r'<[^>]+>', ' ', html)
        
        # 2. Buscamos "Cupón Diario", avanzamos saltando la fecha hasta "Número" y atrapamos los 5 dígitos
        match = re.search(r'Cup[oó]n Diario.*?N[úu]mero.*?(\d{5})', texto_limpio, re.IGNORECASE | re.DOTALL)
        
        return match.group(1) if match else None
    except:
        return None

def comprobar_premio():
    numero_ganador = obtener_numero_once()
    datos = cargar_datos()
    tickets = datos.get("tickets", {})
    stats = datos.get("stats", {})

    if not numero_ganador or not numero_ganador.isdigit() or len(numero_ganador) != 5:
        for chat_id in tickets.keys():
            bot.send_message(chat_id, "⚠️ No he podido verificar el número de la ONCE de hoy automáticamente.")
        return

    for chat_id, ticket in tickets.items():
        if chat_id not in stats:
            stats[chat_id] = {"jugados": 0, "ganados": 0}
        
        stats[chat_id]["jugados"] += 1 
        
        if ticket == numero_ganador[-3:]:
            stats[chat_id]["ganados"] += 1 
            bot.send_message(chat_id, f"¡BINGO! 🎉 ONCE: {numero_ganador}. ¡Tus dígitos ({ticket}) coinciden! 50€ al bolsillo.")
        else:
            bot.send_message(chat_id, f"Hoy no hubo suerte. ONCE: {numero_ganador}, tu ticket: {ticket}.")
            
    datos["tickets"] = {}
    datos["stats"] = stats
    guardar_datos(datos)

def enviar_recordatorio():
    datos = cargar_datos()
    tickets = datos.get("tickets", {})
    stats = datos.get("stats", {})
    for chat_id in stats.keys():
        if chat_id not in tickets:
            try:
                bot.send_message(chat_id, "🔔 *¡Recordatorio diario!* No he detectado ningún ticket a tu nombre para hoy. Acuérdate de registrarlo con `/ticket XXX`.", parse_mode="Markdown")
            except:
                pass

# --- PROGRAMADOR DIARIO ---
def tareas_programadas():
    schedule.every().day.at("15:00").do(enviar_recordatorio)
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
