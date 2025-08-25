import paramiko, nbtlib, io, gzip

host = "na1684.pebblehost.com"
port = 2222
user = "davidyflol@gmail.com.21d76c3e"
pw   = "PowergamE.99"
uuid = "354a27be-9851-3d16-9e87-d8bff48d4c47"  # ⚠️ tu UUID real

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(
    hostname=host,
    port=port,
    username=user,
    password=pw,
    look_for_keys=False,
    allow_agent=False
)

sftp = ssh.open_sftp()
with sftp.open(f"world/playerdata/{uuid}.dat", "rb") as remote_file:
    raw_bytes = remote_file.read()
    # Descomprimir GZip y parsear NBT
    with gzip.GzipFile(fileobj=io.BytesIO(raw_bytes)) as gz:
        nbt = nbtlib.File.parse(gz)

sftp.close()
ssh.close()

forgecaps = nbt.get("ForgeCaps")
if forgecaps and "mmorpg:entity_data" in forgecaps:
    mmorpg = forgecaps["mmorpg:entity_data"]
    print("Level:", int(mmorpg.get("level", -1)))
    print("Exp:", int(mmorpg.get("exp", -1)))
    print("HP:", int(mmorpg.get("hp", -1)))

    energy = None
    if "mmorpg_unit" in mmorpg:
        for _, stat in mmorpg["mmorpg_unit"].items():
            if "i" in stat and str(stat["i"]) == "energy":
                energy = int(float(stat["v"]))
    print("Energy:", energy)