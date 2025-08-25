import os
from dotenv import load_dotenv

load_dotenv()  # esto carga el .env

# FTP/SFTP PebbleHost
FTP_HOST = os.getenv("SFTP_HOST", os.getenv("FTP_HOST", "ftp.pebblehost.com"))
FTP_USER = os.getenv("SFTP_USER", os.getenv("FTP_USER", ""))
FTP_PASS = os.getenv("SFTP_PASS", os.getenv("FTP_PASS", ""))

# Nombre de la carpeta del mundo en tu servidor
WORLD_DIR = os.getenv("WORLD_DIR", "world")

# Cache en memoria (segundos)
CACHE_TTL = int(os.getenv("CACHE_TTL", "60"))

# Consulta al servidor para ver jugadores online (opcional)
ENABLE_QUERY = os.getenv("ENABLE_QUERY", "false").lower() == "true"
MC_HOST = os.getenv("MC_HOST", "51.161.91.248")
MC_PORT = int(os.getenv("MC_PORT", "25565"))
