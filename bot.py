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

# --- GESTIÓN DE BASE DE DATOS (ADAPTADA PARA ESTADÍSTICAS) ---
def cargar_datos():
    url = f"https://api.jsonbin.io/v3/b/{BIN_ID}/latest"
    headers = {"X-Master-Key": API_KEY}
    try:
        res = requests.get(url, headers=headers).json().get('record', {})
        # Si la estructura es antigua o está vacía, la inicializamos de forma segura
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
            
            # Guardamos el ticket diario
            datos["tickets"][chat_id] = numero
            
            # Si es un usuario nuevo, le inicializamos sus estadísticas
            if chat_id not in datos["stats"]:
                datos["stats"][chat_id] = {"jugados": 0, "ganados": 0}
                
            guardar_datos(datos)
            bot.reply_to(message, f"✅ Ticket {numero} guardado. Te aviso a las 22:00.")
        else:
            bot.reply_to(message, "⚠️ Formato incorrecto. Ejemplo: /ticket 482")
    except:
        bot.reply_to(message, "⚠️ Falta el número.")

# [MEJORA 1] Comando para ver el ticket actual
@bot.message_handler(commands=['ver'])
def ver_ticket(message):
    datos = cargar_datos()
    chat_id = str(message.chat.id)
    ticket = datos["tickets"].get(chat_id)
    
    if ticket:
        bot.reply_to(message, f"🎫 Para el sorteo de hoy tienes guardado el número: *{ticket}*", parse_mode="Markdown")
    else:
        bot.reply_to(message, "🔍 Aún no has registrado ningún ticket para hoy. Usa /ticket seguido de tus 3 números.")

# [MEJORA 3] Comando para consultar estadísticas
@bot.message_handler(commands=['stats'])
def ver_estadisticas(message):
    datos = cargar_datos()
    chat_id = str(message.chat.id)
    user_stats = datos["stats"].get(chat_id, {"jugados": 0, "ganados": 0})
    
    jugados = user_stats["jugados"]
    ganados = user_stats["ganados"]
    
    bot.reply_to(message, f"📊 *Tus Estadísticas del Parking:*\n\n"
                          f"🔹 Sorteos jugados: {jugados}\n"
                          f"🏆 Premios ganados: {ganados}", parse_mode="Markdown")

@bot.message_handler(commands=['test'])
def forzar_comprobacion(message):
    bot.reply_to(message, "🔍 Comprobando sorteo en la web oficial de la ONCE...")
    comprobar_premio()

# --- LÓGICA DEL SORTEO Y ALERTAS ---

def obtener_numero_once():
    url = "https://www.juegosonce.es/resultados-cupon-diario"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        html = requests.get(url, headers=headers).text
        match = re.search(r'(?:N[úu]mero|premiado)[^\d]*(\d{5})', html, re.IGNORECASE)
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
            bot.send_message(chat_id, "⚠️ No he podido verificar el número de la ONCE automáticamente.")
        return

    for chat_id, ticket in tickets.items():
        if chat_id not in stats:
            stats[chat_id] = {"jugados": 0, "ganados": 0}
        
        # [MEJORA 3] Sumamos un día jugado en el historial
        stats[chat_id]["jugados"] += 1 
        
        if ticket == numero_ganador[-3:]:
            stats[chat_id]["ganados"] += 1 # Sumamos un premio ganado
            bot.send_message(chat_id, f"¡BINGO! 🎉 ONCE: {numero_ganador}. ¡Tus dígitos ({ticket}) coinciden! 50€ al bolsillo.")
        else:
            bot.send_message(chat_id, f"Hoy no hubo suerte. ONCE: {numero_ganador}, tu ticket: {ticket}.")
            
    # Vaciamos los tickets diarios, pero MANTENEMOS las estadísticas intactas
    datos["tickets"] = {}
    datos["stats"] = stats
    guardar_datos(datos)

# [MEJORA 4] Función de recordatorio automático si te despistas
def enviar_recordatorio():
    datos = cargar_datos()
    tickets = datos.get("tickets", {})
    stats = datos.get("stats", {})
    
    # Enviamos aviso a todos los usuarios conocidos que NO hayan puesto ticket hoy
    for chat_id in stats.keys():
        if chat_id not in tickets:
            try:
                bot.send_message(chat_id, "🔔 *¡Recordatorio diario!* No he detectado ningún ticket a tu nombre para hoy. Si has tenido que aparcar en el parking, acuérdate de registrarlo con `/ticket XXX` antes del sorteo.", parse_mode="Markdown")
            except:
                pass # Por si algún usuario bloqueó al bot

# --- PROGRAMADOR DIARIO ---
def tareas_programadas():
    # [MEJORA 4] Alerta diaria a las 15:00 (ajusta la hora si lo prefieres)
    schedule.every().day.at("15:00").do(enviar_recordatorio)
    
    # Comprobación del sorteo a las 22:00
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