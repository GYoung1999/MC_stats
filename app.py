from flask import Flask, render_template, request, abort
from stats_service import fetch_all_players_summary, fetch_player_details, get_online_players

app = Flask(__name__)

@app.route("/")
def leaderboard():
    sort = request.args.get("sort", "kills")  # "kills" | "level"
    players = fetch_all_players_summary()

    if sort == "level":
        players.sort(key=lambda p: (p["level"] is None, p["level"]), reverse=True)
    else:
        players.sort(key=lambda p: p["mob_kills"], reverse=True)

    return render_template("leaderboard.html", players=players, sort=sort)

@app.route("/players")
def players():
    players = fetch_all_players_summary()
    online_count, online_names = get_online_players()

    # ordenar por nombre
    players.sort(key=lambda p: p["name"].lower())
    online_set = set(n.lower() for n in online_names)

    # 🔹 obtener datos de conexión
    online_count, online_names = get_online_players()

    return render_template("players.html",
                           players=players,
                           online_count=online_count,
                           online_names=online_names,
                           online_set=online_set)

@app.route("/player/<uuid>")
def player_profile(uuid):
    data = fetch_player_details(uuid)
    if not data:
        abort(404)
    return render_template("player.html", data=data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

