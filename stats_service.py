import io
import json
import time
import paramiko
import gzip
from typing import Dict, Any, List, Optional, Tuple
import nbtlib

from config import FTP_HOST, FTP_USER, FTP_PASS, WORLD_DIR, CACHE_TTL, ENABLE_QUERY, MC_HOST, MC_PORT
# Opcional: para jugadores online
try:
    from mcstatus import JavaServer
except Exception:
    JavaServer = None

# ------- Utilidades -------

def human_time_from_ticks(ticks: int) -> str:
    # 20 ticks = 1 segundo
    seconds = ticks / 20
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def meters_from_cm(cm: int) -> float:
    return cm / 100.0

def km_from_cm(cm: int) -> float:
    return cm / 100000.0

def nice_name(item_id: str) -> str:
    # "minecraft:zombie" -> "Zombie"
    name = item_id.split(":")[-1].replace("_", " ").strip()
    return name.capitalize()

def compute_vanilla_level_from_xp_total(xp_total: int) -> int:
    level = 0
    while True:
        if level <= 16:
            need = level*level + 6*level
        elif level <= 31:
            need = int(2.5*level*level - 40.5*level + 360)
        else:
            need = int(4.5*level*level - 162.5*level + 2220)
        if need > xp_total:
            return max(0, level-1)
        level += 1

# ------- Cliente SFTP con Paramiko -------

class FTPClient:
    def __init__(self):
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(
            FTP_HOST,
            port=2222,  # Puerto de SFTP en PebbleHost
            username=FTP_USER,
            password=FTP_PASS,
            look_for_keys=False,
            allow_agent=False,
            timeout=20
        )
        self.sftp = self.ssh.open_sftp()

    def close(self):
        try:
            self.sftp.close()
            self.ssh.close()
        except Exception:
            pass

    def read_binary(self, path: str) -> bytes:
        with self.sftp.open(path, "rb") as f:
            return f.read()

    def list_files(self, path: str) -> List[str]:
        return self.sftp.listdir(path)

# ------- Cache simple en memoria -------

_cache: Dict[str, Tuple[float, Any]] = {}

def cache_get(key: str):
    now = time.time()
    if key in _cache:
        t, val = _cache[key]
        if now - t < CACHE_TTL:
            return val
        else:
            del _cache[key]
    return None

def cache_set(key: str, val: Any):
    _cache[key] = (time.time(), val)

# ------- Carga base de datos del server -------

def load_usercache(ftp: FTPClient) -> Dict[str, str]:
    key = "usercache"
    cached = cache_get(key)
    if cached is not None:
        return cached

    data = {}
    try:
        raw = ftp.read_binary("usercache.json")
        arr = json.loads(raw.decode("utf-8"))
        for entry in arr:
            uuid = entry.get("uuid")
            name = entry.get("name")
            if uuid and name:
                data[uuid] = name
    except Exception:
        pass

    cache_set(key, data)
    return data

def list_player_uuids(ftp: FTPClient) -> List[str]:
    stats_path = f"{WORLD_DIR}/stats"
    files = ftp.list_files(stats_path)
    uuids = []
    for f in files:
        if f.endswith(".json"):
            uuids.append(f[:-5])
    return uuids

def load_stats_json(ftp: FTPClient, uuid: str) -> Optional[Dict[str, Any]]:
    key = f"stats:{uuid}"
    cached = cache_get(key)
    if cached is not None:
        return cached

    path = f"{WORLD_DIR}/stats/{uuid}.json"
    try:
        raw = ftp.read_binary(path)
        obj = json.loads(raw.decode("utf-8"))
        cache_set(key, obj.get("stats", obj))
        return cache_get(key)
    except Exception:
        return None

def load_player_nbt(ftp: FTPClient, uuid: str):
    key = f"nbt:{uuid}"
    cached = cache_get(key)
    if cached is not None:
        return cached
    path = f"{WORLD_DIR}/playerdata/{uuid}.dat"
    try:
        raw = ftp.read_binary(path)
        buf = io.BytesIO(raw)
        # ✅ Descomprimir con gzip (igual que en test.py)
        with gzip.GzipFile(fileobj=buf) as gz:
            nbt = nbtlib.File.parse(gz)
        cache_set(key, nbt)
        return nbt
    except Exception as e:
        print("DEBUG load_player_nbt error:", e)
        return None

# ------- Extracción de métricas -------

def extract_vanilla_metrics(stats: Dict[str, Any]) -> Dict[str, Any]:
    custom = stats.get("minecraft:custom", {})
    killed = stats.get("minecraft:killed", {})
    picked_up = stats.get("minecraft:picked_up", {})

    mob_kills = int(custom.get("minecraft:mob_kills", 0))
    deaths = int(custom.get("minecraft:deaths", 0))
    play_time_ticks = int(custom.get("minecraft:play_time", 0))
    walk_cm = int(custom.get("minecraft:walk_one_cm", 0))
    fly_cm = int(custom.get("minecraft:fly_one_cm", 0))
    jumps = int(custom.get("minecraft:jump", 0))

    top_mobs = sorted(
        ((nice_name(k), int(v)) for k, v in killed.items()),
        key=lambda x: x[1],
        reverse=True
    )[:10]

    coins = {}
    for k, v in picked_up.items():
        if k.startswith("lightmanscurrency:coin"):
            coins[nice_name(k)] = coins.get(nice_name(k), 0) + int(v)

    return {
        "mob_kills": mob_kills,
        "deaths": deaths,
        "play_time_ticks": play_time_ticks,
        "play_time_hms": human_time_from_ticks(play_time_ticks),
        "walk_km": round(km_from_cm(walk_cm), 2),
        "fly_km": round(km_from_cm(fly_cm), 2),
        "jumps": jumps,
        "top_mobs": top_mobs,
        "coins": coins
    }

def extract_mod_level_and_xp(nbt_obj) -> Dict[str, Any]:
    """
    Extrae datos del mod Mine and Slash (Craft to Exile 2):
    nivel, experiencia, vida y energía.
    """
    level_mod = None
    xp_mod = None
    hp = None
    energy = None

    try:
        root = nbt_obj.root if hasattr(nbt_obj, "root") else nbt_obj
        forgecaps = root.get("ForgeCaps")

        if forgecaps and "mmorpg:entity_data" in forgecaps:
            mmorpg = forgecaps["mmorpg:entity_data"]

            def safe_int(x, default=None):
                try:
                    return int(float(x))
                except Exception:
                    return default

            level_mod = safe_int(mmorpg.get("level"))
            xp_mod   = safe_int(mmorpg.get("exp"))
            hp       = safe_int(mmorpg.get("hp"))

            if "mmorpg_unit" in mmorpg:
                for _, stat in mmorpg["mmorpg_unit"].items():
                    if "i" in stat and str(stat["i"]) == "energy":
                        energy = safe_int(stat.get("v"))
                        break

    except Exception as e:
        print("DEBUG extract_mod_level_and_xp error:", e)

    return {
        "level_mod": level_mod,
        "xp_mod": xp_mod,
        "hp": hp,
        "energy": energy
    }

# ------- API de alto nivel para Flask -------

def fetch_all_players_summary() -> List[Dict[str, Any]]:
    ftp = FTPClient()
    try:
        uuids = list_player_uuids(ftp)
        name_map = load_usercache(ftp)

        players = []
        for uuid in uuids:
            stats_json = load_stats_json(ftp, uuid)
            if not stats_json:
                continue
            vanilla = extract_vanilla_metrics(stats_json)

            nbt = load_player_nbt(ftp, uuid)
            modinfo = extract_mod_level_and_xp(nbt) if nbt else {}

            players.append({
                "uuid": uuid,
                "name": name_map.get(uuid, uuid[:8]),
                "mob_kills": vanilla["mob_kills"],
                "deaths": vanilla["deaths"],
                "level": modinfo.get("level_mod"),
                "xp": modinfo.get("xp_mod"),
                "hp": modinfo.get("hp"),
                "energy": modinfo.get("energy"),
            })
        return players
    finally:
        ftp.close()

def fetch_player_details(uuid: str) -> Optional[Dict[str, Any]]:
    ftp = FTPClient()
    try:
        name_map = load_usercache(ftp)
        stats_json = load_stats_json(ftp, uuid)
        if not stats_json:
            return None
        vanilla = extract_vanilla_metrics(stats_json)
        nbt = load_player_nbt(ftp, uuid)
        modinfo = extract_mod_level_and_xp(nbt) if nbt else {}

        return {
            "uuid": uuid,
            "name": name_map.get(uuid, uuid[:8]),
            "vanilla": vanilla,
            "mod": modinfo
        }
    finally:
        ftp.close()

def get_online_players() -> Tuple[int, List[str]]:
    if not (ENABLE_QUERY and JavaServer):
        return (0, [])
    try:
        server = JavaServer.lookup(f"{MC_HOST}:{MC_PORT}")
        status = server.status()
        count = status.players.online or 0
        sample_names = []
        if status.players.sample:
            sample_names = [p.name for p in status.players.sample]
        return (count, sample_names)
    except Exception:
        return (0, [])
