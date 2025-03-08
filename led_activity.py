import RPi.GPIO as GPIO
import time
import threading
import signal
import sys
import inotify.adapters
import inotify.constants

# Configurazione
LED_PIN = 17
WATCHED_FILE = "/home/pi/sismografo.db"
DEBOUNCE_SECONDS = 1.0  # Tempo di attesa per il debounce

# Setup GPIO: LED acceso di default
GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.output(LED_PIN, GPIO.HIGH)

# Variabili per la gestione del debounce
debounce_timer = None
debounce_lock = threading.Lock()

def blink_pattern():
    """
    Esegue un pattern specifico sul LED, ad esempio tre lampeggi rapidi.
    """
    # Pattern: tre lampeggi rapidi
    for _ in range(3):
        GPIO.output(LED_PIN, GPIO.LOW)
        time.sleep(0.1)
        GPIO.output(LED_PIN, GPIO.HIGH)
        time.sleep(0.1)

def schedule_blink():
    """
    Pianifica l'esecuzione del pattern LED.
    Se esiste già un timer in sospeso, lo annulla e ne crea uno nuovo.
    In questo modo, durante una valanga di eventi, il pattern verrà eseguito una volta sola,
    dopo che sono trascorsi DEBOUNCE_SECONDS senza ulteriori eventi.
    """
    global debounce_timer
    with debounce_lock:
        if debounce_timer is not None:
            debounce_timer.cancel()
        debounce_timer = threading.Timer(DEBOUNCE_SECONDS, blink_pattern)
        debounce_timer.start()

def file_watcher():
    """
    Monitora il file WATCHED_FILE per eventi:
    IN_ACCESS, IN_MODIFY, IN_OPEN, IN_CLOSE_WRITE e IN_CLOSE_NOWRITE.
    Al verificarsi di uno di questi eventi, viene richiamata la funzione schedule_blink().
    """
    notifier = inotify.adapters.Inotify()
    mask = (inotify.constants.IN_ACCESS |
            inotify.constants.IN_MODIFY |
            inotify.constants.IN_OPEN |
            inotify.constants.IN_CLOSE_WRITE |
            inotify.constants.IN_CLOSE_NOWRITE)
    notifier.add_watch(WATCHED_FILE, mask=mask)
    
    for event in notifier.event_gen(yield_nones=False):
        (_, type_names, path, filename) = event
        if any(ev in type_names for ev in ['IN_ACCESS', 'IN_MODIFY', 'IN_OPEN', 'IN_CLOSE_WRITE', 'IN_CLOSE_NOWRITE']):
            schedule_blink()

def clean_exit(signum, frame):
    """
    Funzione di pulizia in uscita: termina eventuali timer, spegne il LED e pulisce i GPIO.
    """
    global debounce_timer
    if debounce_timer is not None:
        debounce_timer.cancel()
    GPIO.output(LED_PIN, GPIO.LOW)
    GPIO.cleanup()
    sys.exit(0)

# Gestione dei segnali di terminazione
signal.signal(signal.SIGINT, clean_exit)
signal.signal(signal.SIGTERM, clean_exit)

# Avvia il thread del file watcher
watcher_thread = threading.Thread(target=file_watcher)
watcher_thread.daemon = True
watcher_thread.start()

# Loop principale: mantiene il programma in esecuzione in attesa degli eventi
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    clean_exit(None, None)

