from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import threading
import time
import random
import math
from ml.traffic_predictor import TrafficPredictor
from traffic_graph import TrafficGraph

app = Flask(__name__)
CORS(app)

JUNCTIONS = {
    "vr_mall":        {"name": "VR Mall",                            "lat": 21.145645, "lng": 72.759342},
    "rr-mall":        {"name": "RR Mall / Lalbhai Contractar Stadium","lat": 21.156747, "lng": 72.766708},
    "big_bazaar":     {"name": "Big Bazaar",                         "lat": 21.159575, "lng": 72.771122},
    "kargil_chowk":   {"name": "Kargil Chowk",                       "lat": 21.164589, "lng": 72.779597},
    "svnit":          {"name": "SVNIT / Keval Chowk",                "lat": 21.167709, "lng": 72.784981},
    "jani_locha":     {"name": "Jani Locha House",                   "lat": 21.173061, "lng": 72.792862},
    "parle_point":    {"name": "Parle Point Circle",                 "lat": 21.174087, "lng": 72.793784},
    "amrut_fashion":  {"name": "Amrut Fashion / Cable Bridge",       "lat": 21.178134, "lng": 72.798094},
    "sarvajanik":     {"name": "Sarvajanik College",                 "lat": 21.184766, "lng": 72.808180},
    "athwa_gate":     {"name": "Athwa Gate",                         "lat": 21.185737, "lng": 72.810701},
    "iti":            {"name": "ITI Surat / S.S. Gandhi college",    "lat": 21.180304, "lng": 72.818758},
    "civil_hospital": {"name": "Civil Hospital",                     "lat": 21.180985, "lng": 72.824251},
    "avadh_arkelia":  {"name": "Avadh Arkelia",                      "lat": 21.149216, "lng": 72.768396},
    "sangini_edge":   {"name": "Sangini Edge",                       "lat": 21.150767, "lng": 72.772162},
    "someshwar_cir":  {"name": "Someshwar Circle",                   "lat": 21.153567, "lng": 72.778951},
    "anuvrat_dwar":   {"name": "Arunvrat Dwar",                      "lat": 21.159955, "lng": 72.796475},
    "breadliner_cir": {"name": "Breadliner Circle",                  "lat": 21.161261, "lng": 72.803203},
    "bharat_char_rasta":{"name": "Bhatar Char Rasta",                "lat": 21.162807, "lng": 72.812066},
    "navjvan_cir":    {"name": "Navjvan Circle",                     "lat": 21.167758, "lng": 72.820734},
    "sosyo_cir":      {"name": "Sosyo Circle",                       "lat": 21.172459, "lng": 72.826751},
    "vesu_police_st": {"name": "Vesu Police Station",                "lat": 21.166227, "lng": 72.802601},
    "kp_group_cir":   {"name": "KP Group Circle",                    "lat": 21.168199, "lng": 72.806930},
    "rupali_canal":   {"name": "Rupali Canal",                       "lat": 21.169742, "lng": 72.811611},
    "canal_bhatar-rd_cir":{"name": "Canal-Bhatar Rd Circle",         "lat": 21.170825, "lng": 72.815808},
    "amaazia_waterpark_cir":{"name": "Amaazia Water Park Junction",  "lat": 21.170467, "lng": 72.794881},
    "rangila_park":   {"name": "Rangila Park",                       "lat": 21.175007, "lng": 72.805293},
    "ram_chowk":      {"name": "Ram Chowk",                          "lat": 21.175720, "lng": 72.810975},
    "poddar_plaza":   {"name": "Poddar Plaza",                       "lat": 21.176593, "lng": 72.819039},
    "sai_dham_canal": {"name": "Shree Saidhaam - Vesu Canal",        "lat": 21.171978, "lng": 72.819990},
    "rokadiya_hanuman":{"name": "Rokadiya Hanuman Temple",           "lat": 21.178037, "lng": 72.834197},
}

ROADS = [
    ("vr_mall","rr-mall",1.45),("rr-mall","big_bazaar",0.6),("big_bazaar","kargil_chowk",1.1),
    ("kargil_chowk","svnit",0.7),("rr-mall","avadh_arkelia",0.9),("big_bazaar","sangini_edge",1.0),
    ("kargil_chowk","someshwar_cir",1.3),("svnit","jani_locha",1.0),("jani_locha","parle_point",0.2),
    ("parle_point","amrut_fashion",0.7),("amrut_fashion","sarvajanik",1.4),("sarvajanik","athwa_gate",0.35),
    ("athwa_gate","iti",1.0),("iti","civil_hospital",0.6),("iti","poddar_plaza",0.7),
    ("civil_hospital","sosyo_cir",1.0),("vr_mall","avadh_arkelia",1.0),("avadh_arkelia","sangini_edge",0.4),
    ("sangini_edge","someshwar_cir",0.8),("someshwar_cir","anuvrat_dwar",1.9),
    ("anuvrat_dwar","breadliner_cir",0.85),("anuvrat_dwar","vesu_police_st",1.1),
    ("breadliner_cir","vesu_police_st",0.5),("kp_group_cir","vesu_police_st",0.6),
    ("kp_group_cir","rupali_canal",0.55),("rupali_canal","canal_bhatar-rd_cir",0.44),
    ("sai_dham_canal","canal_bhatar-rd_cir",0.4),("poddar_plaza","canal_bhatar-rd_cir",0.75),
    ("poddar_plaza","sai_dham_canal",0.5),("breadliner_cir","bharat_char_rasta",1.0),
    ("bharat_char_rasta","navjvan_cir",1.1),("bharat_char_rasta","rupali_canal",0.8),
    ("bharat_char_rasta","canal_bhatar-rd_cir",1.0),("navjvan_cir","sosyo_cir",0.9),
    ("navjvan_cir","sai_dham_canal",0.5),("amaazia_waterpark_cir","anuvrat_dwar",1.3),
    ("amaazia_waterpark_cir","jani_locha",0.35),("amaazia_waterpark_cir","rangila_park",1.3),
    ("parle_point","rangila_park",1.2),("ram_chowk","rangila_park",0.6),
    ("kp_group_cir","rangila_park",0.8),("ram_chowk","poddar_plaza",0.9),
    ("ram_chowk","rupali_canal",0.7),
]

# ── Build adjacency and road-distance lookup ──────────────────────────────────
def build_adjacency():
    adj = {jid: [] for jid in JUNCTIONS}
    for a, b, _ in ROADS:
        if a in adj and b in JUNCTIONS:
            if b not in adj[a]: adj[a].append(b)
        if b in adj and a in JUNCTIONS:
            if a not in adj[b]: adj[b].append(a)
    return adj

ADJACENCY = build_adjacency()

# Fast road-distance lookup for cumulative-km calculations
_ROAD_KM = {}
for _a, _b, _d in ROADS:
    _ROAD_KM[(_a, _b)] = _d
    _ROAD_KM[(_b, _a)] = _d

predictor = TrafficPredictor()
graph     = TrafficGraph(JUNCTIONS, ROADS)

# ── Constants ─────────────────────────────────────────────────────────────────
YELLOW_DURATION      = 3
MIN_GREEN            = 18
MAX_GREEN            = 60
JUNCTION_VEHICLE_THRESHOLD = 200   # total vehicles per junction must not exceed this
ZERO_BLINK_SECS      = 4
CORRIDOR_TTL         = 180     # seconds until corridor auto-expires
AMB_MOVE_INTERVAL    = 6       # seconds per junction (ambulance)
VIP_MOVE_INTERVAL    = 8       # seconds per junction (VIP convoy)
PRIORITY_AHEAD       = 2       # junctions ahead to pre-clear
UPSTREAM_RELEASE_KM  = 1.0     # km ambulance must travel past a junction to release its upstream block
AMB_TRAILING_RELEASE_KM = 1.0  # km ambulance must travel past a corridor junction to return it to normal
VIP_TRAILING_RELEASE_KM = 2.0  # km VIP convoy must travel past a locked junction to return it to normal
AMB_SPEED_CORRIDOR   = 50.0    # km/h ambulance speed during green corridor (for ETA calc)

# ── Corridor state ─────────────────────────────────────────────────────────────
_corridor_seq        = 0
ambulance_corridors  = {}   # cid → record
vip_corridors        = {}   # cid → record
junction_ambulance   = {}   # jid → {corridor_id, green_toward}   ← corridor junction override
junction_vip         = {}   # jid → {corridor_id, green_toward}   ← VIP corridor override
junction_upstream    = {}   # jid → {corridor_id, type, toward_jid, release_at_km}  ← upstream feeder block
_corridor_lock       = threading.Lock()

# ── Jam simulation state ──────────────────────────────────────────────────────
_rupali_jam_active   = False           # True while jam demo is active
_rupali_jam_lock     = threading.Lock()
RUPALI_JAM_VEHICLES  = 195            # vehicles per road during jam (max per-road)
# Neighbouring junctions also choked during jam (makes reroute obvious)
RUPALI_JAM_NEIGHBORS = ["kp_group_cir", "ram_chowk", "canal_bhatar-rd_cir", "bharat_char_rasta"]
RUPALI_JAM_NBR_VEHICLES = 150        # neighbor junction vehicles during jam


# ── Hardware-driven junctions ────────────────────────────────────────────────
# Junctions in this set have real IR sensor data injected via /api/sensor_update.
# The simulation loop skips random arrivals for these junctions;
# all corridor/VIP/upstream overrides still apply normally.
HARDWARE_JUNCTIONS   = set()   # populated at runtime by /api/sensor_update


# ── Helpers ───────────────────────────────────────────────────────────────────
def _path_cumkm(path):
    """Cumulative km at each junction index in path."""
    cumkm = [0.0]
    for i in range(len(path) - 1):
        d = _ROAD_KM.get((path[i], path[i+1]),
            _ROAD_KM.get((path[i+1], path[i]), 0.5))
        cumkm.append(cumkm[-1] + d)
    return cumkm


def _corridor_current_km(rec, move_interval):
    """Interpolated km the vehicle has traveled so far in this corridor."""
    cumkm = rec.get("cumkm", [0.0])
    pos   = rec["position_idx"]
    if pos >= len(cumkm):
        return cumkm[-1]
    frac = min(1.0, (time.time() - rec["last_moved"]) / move_interval)
    if pos < len(cumkm) - 1:
        return cumkm[pos] + frac * (cumkm[pos + 1] - cumkm[pos])
    return cumkm[pos]


def _reset_junction_to_adaptive(jid):
    """Immediately returns a junction to adaptive mode on the next tick."""
    if jid in junction_state:
        s = junction_state[jid]
        s["phase"]          = "red"
        s["countdown"]      = 1   # expires next tick → adaptive logic runs
        s["green_duration"] = 1
        s["zero_since"]     = None


# ── Upstream feeder blocking ──────────────────────────────────────────────────
def _apply_upstream_blocks(cid, corridor_type, path, cumkm, window_start, window_end):
    """
    For every corridor junction in [window_start, window_end), find its
    neighbours that are NOT on the path (upstream feeders) and block them.
    They stay blocked until the vehicle has traveled UPSTREAM_RELEASE_KM
    past that corridor junction.

    MUST be called while _corridor_lock is held.
    """
    path_set = set(path)
    for i in range(window_start, min(window_end, len(path))):
        corridor_jid  = path[i]
        release_km    = cumkm[i] + UPSTREAM_RELEASE_KM
        for feeder_jid in ADJACENCY.get(corridor_jid, []):
            if feeder_jid not in path_set:
                junction_upstream[feeder_jid] = {
                    "corridor_id": cid,
                    "type":        corridor_type,
                    "toward_jid":  corridor_jid,
                    "release_at_km": release_km,
                }


def _release_stale_upstream_blocks():
    """
    Called once per simulation tick (outside _corridor_lock).
    Releases any upstream feeder blocks where the corridor vehicle has
    already traveled UPSTREAM_RELEASE_KM past the blocked junction.
    """
    # Compute current km for every active corridor
    corridor_km = {}
    for cid, rec in ambulance_corridors.items():
        corridor_km[cid] = _corridor_current_km(rec, AMB_MOVE_INTERVAL)
    for cid, rec in vip_corridors.items():
        corridor_km[cid] = _corridor_current_km(rec, VIP_MOVE_INTERVAL)

    to_release = [jid for jid, blk in junction_upstream.items()
                  if corridor_km.get(blk["corridor_id"], 0) >= blk["release_at_km"]]
    for jid in to_release:
        del junction_upstream[jid]
        _reset_junction_to_adaptive(jid)


def _clear_upstream_for_corridor(cid):
    """Remove all upstream blocks belonging to corridor cid (lock must be held)."""
    stale = [jid for jid, blk in junction_upstream.items() if blk["corridor_id"] == cid]
    for jid in stale:
        del junction_upstream[jid]
        _reset_junction_to_adaptive(jid)


# ── Ambulance priority window ─────────────────────────────────────────────────
def _apply_priority_window(cid):
    """
    (Re-)compute the ambulance green-corridor window.
    Must be called while _corridor_lock is held.

    Trailing edge: distance-based — a junction is released as soon as the
    ambulance has traveled AMB_TRAILING_RELEASE_KM (1 km) past it, instead
    of the old fixed "pos-1" rule that kept signals overridden until the
    ambulance had crossed one full extra junction.

    Leading edge: pos + PRIORITY_AHEAD (2 junctions ahead pre-cleared).
    Upstream feeders are blocked and released at +1 km.
    """
    rec = ambulance_corridors.get(cid)
    if not rec:
        return
    path   = rec["path"]
    pos    = rec["position_idx"]
    cumkm  = rec["cumkm"]

    # Current ambulance km along the path (at the junction it just reached)
    current_km = cumkm[pos] if pos < len(cumkm) else cumkm[-1]

    # ── Trailing window: distance-based ──────────────────────────────────────
    # Include all preceding junctions that are within AMB_TRAILING_RELEASE_KM
    # behind the ambulance.  Any junction farther back is immediately released.
    window_start = pos   # default: no trailing junctions kept
    for i in range(pos - 1, -1, -1):
        if current_km - cumkm[i] < AMB_TRAILING_RELEASE_KM:
            window_start = i   # this junction is still within 1 km — keep it
        else:
            break              # farther than 1 km — stop looking back

    window_end = min(pos + PRIORITY_AHEAD + 1, len(path) - 1)

    # Release junctions that have slid out of the trailing edge
    stale = [jid for jid, ov in junction_ambulance.items()
             if ov["corridor_id"] == cid and jid not in path[window_start:]]
    for jid in stale:
        del junction_ambulance[jid]
        _reset_junction_to_adaptive(jid)

    # Apply green overrides for window junctions
    for i in range(window_start, window_end):
        jid    = path[i]
        toward = path[i + 1]
        junction_ambulance[jid] = {"corridor_id": cid, "green_toward": toward}

    # Block upstream feeders for every window junction
    _apply_upstream_blocks(cid, "ambulance", path, cumkm, window_start, window_end + 1)


# ── VIP priority window ───────────────────────────────────────────────────────
def _apply_vip_window(cid):
    """
    (Re-)compute the VIP convoy window.
    Must be called while _corridor_lock is held.

    Trailing edge: distance-based — a locked junction is released as soon as
    the convoy has traveled VIP_TRAILING_RELEASE_KM (2 km) past it, instead
    of the old fixed "pos-1" rule.

    Leading edge: pos + PRIORITY_AHEAD (2 junctions ahead pre-locked).
    Upstream feeders are blocked and released at +1 km.
    """
    rec = vip_corridors.get(cid)
    if not rec:
        return
    path  = rec["path"]
    pos   = rec["position_idx"]
    cumkm = rec["cumkm"]

    # Current convoy km along the path (at the junction it just reached)
    current_km = cumkm[pos] if pos < len(cumkm) else cumkm[-1]

    # ── Trailing window: distance-based ──────────────────────────────────────
    # Keep all preceding junctions within VIP_TRAILING_RELEASE_KM (2 km).
    # Any junction farther back is immediately released to normal operation.
    window_start = pos   # default: no trailing junctions kept
    for i in range(pos - 1, -1, -1):
        if current_km - cumkm[i] < VIP_TRAILING_RELEASE_KM:
            window_start = i   # within 2 km — keep locked
        else:
            break              # beyond 2 km — release

    window_end = min(pos + PRIORITY_AHEAD + 1, len(path))

    # Release stale VIP junctions
    stale = [jid for jid, ov in junction_vip.items()
             if ov["corridor_id"] == cid and jid not in path[window_start:]]
    for jid in stale:
        del junction_vip[jid]
        _reset_junction_to_adaptive(jid)

    # Apply RED-all overrides for window junctions (VIP = total lockdown)
    for i in range(window_start, window_end):
        jid = path[i]
        junction_vip[jid] = {
            "corridor_id":  cid,
            "green_toward": path[i + 1] if i < len(path) - 1 else None,
        }

    # Block upstream feeders
    _apply_upstream_blocks(cid, "vip", path, cumkm, window_start, window_end)


# ── Corridor activation ───────────────────────────────────────────────────────
def _activate_corridor(src, dst):
    """Activate an ambulance green corridor src→dst. Returns (cid, None) or (None, err)."""
    global _corridor_seq
    flat = {jid: 0 for jid in JUNCTIONS}
    path, dist, _ = graph.shortest_path(src, dst, flat)
    if not path or path[0] != src:
        return None, "No path found between the selected junctions"

    now = time.time()
    with _corridor_lock:
        _corridor_seq += 1
        cid = f"AMB-{_corridor_seq:03d}"
        ambulance_corridors[cid] = {
            "id":           cid,
            "from":         src,
            "from_name":    JUNCTIONS[src]["name"],
            "to":           dst,
            "to_name":      JUNCTIONS[dst]["name"],
            "path":         path,
            "distance_km":  round(dist, 2),
            "cumkm":        _path_cumkm(path),
            "created_at":   now,
            "expires_at":   now + CORRIDOR_TTL,
            "ttl":          CORRIDOR_TTL,
            "position_idx": 0,
            "last_moved":   now,
        }
        _apply_priority_window(cid)
    return cid, None


def _activate_vip_corridor(src, dst):
    """Activate a VIP convoy corridor src→dst. Returns (cid, None) or (None, err)."""
    global _corridor_seq
    flat = {jid: 0 for jid in JUNCTIONS}
    path, dist, _ = graph.shortest_path(src, dst, flat)
    if not path or path[0] != src:
        return None, "No path found between the selected junctions"

    now = time.time()
    with _corridor_lock:
        _corridor_seq += 1
        cid = f"VIP-{_corridor_seq:03d}"
        vip_corridors[cid] = {
            "id":           cid,
            "type":         "vip",
            "from":         src,
            "from_name":    JUNCTIONS[src]["name"],
            "to":           dst,
            "to_name":      JUNCTIONS[dst]["name"],
            "path":         path,
            "distance_km":  round(dist, 2),
            "cumkm":        _path_cumkm(path),
            "created_at":   now,
            "expires_at":   now + CORRIDOR_TTL,
            "ttl":          CORRIDOR_TTL,
            "position_idx": 0,
            "last_moved":   now,
        }
        _apply_vip_window(cid)
    return cid, None


# ── Corridor teardown ─────────────────────────────────────────────────────────
def _clear_corridor(cid):
    with _corridor_lock:
        if cid not in ambulance_corridors:
            return False
        stale = [jid for jid, ov in junction_ambulance.items() if ov["corridor_id"] == cid]
        for jid in stale:
            del junction_ambulance[jid]
            _reset_junction_to_adaptive(jid)
        _clear_upstream_for_corridor(cid)
        del ambulance_corridors[cid]
    return True


def _clear_vip_corridor(cid):
    with _corridor_lock:
        if cid not in vip_corridors:
            return False
        stale = [jid for jid, ov in junction_vip.items() if ov["corridor_id"] == cid]
        for jid in stale:
            del junction_vip[jid]
            _reset_junction_to_adaptive(jid)
        _clear_upstream_for_corridor(cid)
        del vip_corridors[cid]
    return True


# ── Corridor tick (advance vehicle positions) ─────────────────────────────────
def _tick_corridors():
    now      = time.time()
    amb_done = []
    vip_done = []

    with _corridor_lock:
        for cid, rec in list(ambulance_corridors.items()):
            path = rec["path"]
            pos  = rec["position_idx"]
            if pos >= len(path) - 1:
                amb_done.append(cid)
                continue
            if now - rec["last_moved"] >= AMB_MOVE_INTERVAL:
                rec["position_idx"] += 1
                rec["last_moved"]    = now
                _apply_priority_window(cid)
                if rec["position_idx"] >= len(path) - 1:
                    amb_done.append(cid)

        for cid, rec in list(vip_corridors.items()):
            path = rec["path"]
            pos  = rec["position_idx"]
            if pos >= len(path) - 1:
                vip_done.append(cid)
                continue
            if now - rec["last_moved"] >= VIP_MOVE_INTERVAL:
                rec["position_idx"] += 1
                rec["last_moved"]    = now
                _apply_vip_window(cid)
                if rec["position_idx"] >= len(path) - 1:
                    vip_done.append(cid)

    for cid in amb_done:
        _clear_corridor(cid)
    for cid in vip_done:
        _clear_vip_corridor(cid)


def _expire_corridors():
    now = time.time()
    for cid in [c for c, r in ambulance_corridors.items() if r["expires_at"] <= now]:
        _clear_corridor(cid)
    for cid in [c for c, r in vip_corridors.items() if r["expires_at"] <= now]:
        _clear_vip_corridor(cid)


# ── Time-of-day traffic multiplier ────────────────────────────────────────────
def get_traffic_multiplier(hour, minute, is_weekend):
    if is_weekend:
        if   0  <= hour <  7:  base = 0.15
        elif 7  <= hour < 10:  base = 0.35
        elif 10 <= hour < 12:  base = 0.65
        elif 12 <= hour < 15:  base = 0.90
        elif 15 <= hour < 17:  base = 0.75
        elif 17 <= hour < 21:  base = 1.00
        elif 21 <= hour < 23:  base = 0.55
        else:                  base = 0.20
    else:
        if   0  <= hour <  6:  base = 0.10
        elif 6  <= hour <  8:  base = 0.55
        elif 8  <= hour < 10:  base = 1.00
        elif 10 <= hour < 12:  base = 0.70
        elif 12 <= hour < 14:  base = 0.60
        elif 14 <= hour < 17:  base = 0.65
        elif 17 <= hour < 20:  base = 1.00
        elif 20 <= hour < 22:  base = 0.55
        else:                  base = 0.20
    ripple = 0.05 * math.sin((minute / 60.0) * math.pi * 2)
    return max(0.1, base + ripple)


def compute_green_time(vehicles, hour):
    g, _ = predictor.predict_green_times_by_vehicles(vehicles, hour)
    return max(MIN_GREEN, min(MAX_GREEN, g))


# ── Traffic state initialisation ──────────────────────────────────────────────
junction_state = {}

def init_traffic():
    t          = time.localtime()
    hour       = t.tm_hour
    is_weekend = (t.tm_wday >= 5)
    mult       = get_traffic_multiplier(hour, t.tm_min, is_weekend)

    for jid in JUNCTIONS:
        roads         = list(ADJACENCY[jid])
        road_vehicles = {r: max(5, round(random.randint(25, 80) * mult)) for r in roads}
        # Enforce initial threshold so simulation starts within the cap
        _init_total = sum(road_vehicles.values())
        if _init_total > JUNCTION_VEHICLE_THRESHOLD:
            _ratio = JUNCTION_VEHICLE_THRESHOLD / _init_total
            road_vehicles = {r: max(0, int(v * _ratio)) for r, v in road_vehicles.items()}
        active_idx    = random.randint(0, max(0, len(roads) - 1)) if roads else 0

        if roads:
            veh       = road_vehicles[roads[active_idx]]
            green_dur = compute_green_time(veh, hour)
            countdown = random.randint(1, green_dur)
        else:
            green_dur = 30
            countdown = 30

        junction_state[jid] = {
            "roads":          roads,
            "road_vehicles":  road_vehicles,
            "active_idx":     active_idx,
            "phase":          "green",
            "countdown":      countdown,
            "green_duration": green_dur,
            "zero_since":     None,
            "quiet_ticks":    {r: 0 for r in roads},
        }

init_traffic()


# ── Per-junction vehicle cap ──────────────────────────────────────────────────
def _apply_junction_threshold(st):
    """Clamp total vehicles at this junction to JUNCTION_VEHICLE_THRESHOLD.

    If the sum across all roads exceeds the threshold, each road is scaled
    down proportionally so that departures always win over arrivals once the
    cap is reached — traffic decreases instead of growing without bound.
    """
    roads = st["road_vehicles"]
    total = sum(roads.values())
    if total > JUNCTION_VEHICLE_THRESHOLD:
        ratio = JUNCTION_VEHICLE_THRESHOLD / total
        for r in roads:
            roads[r] = max(0, int(roads[r] * ratio))


# ── Main simulation loop ──────────────────────────────────────────────────────
def update_traffic():
    while True:
        t          = time.localtime()
        hour       = t.tm_hour
        minute     = t.tm_min
        is_weekend = (t.tm_wday >= 5)
        mult       = get_traffic_multiplier(hour, minute, is_weekend)

        _expire_corridors()
        _tick_corridors()
        _release_stale_upstream_blocks()   # km-based upstream release

        for jid, st in junction_state.items():
            roads = st["roads"]
            if not roads:
                continue

            # ── Priority 1: Ambulance corridor override ────────────────────────
            # Active road gets forced GREEN toward next hop.
            # All other roads at this junction stay RED (handled in _build_api).
            # Skip all normal phase-transition logic.
            amb = junction_ambulance.get(jid)
            if amb:
                toward = amb["green_toward"]
                if toward in roads:
                    st["active_idx"]     = roads.index(toward)
                    st["phase"]          = "green"
                    st["countdown"]      = AMB_MOVE_INTERVAL
                    st["green_duration"] = AMB_MOVE_INTERVAL
                    st["zero_since"]     = None

                active_road = roads[st["active_idx"]]
                if "quiet_ticks" not in st:
                    st["quiet_ticks"] = {r: 0 for r in roads}

                for r in roads:
                    v        = st["road_vehicles"][r]
                    is_green = (r == active_road)
                    qt = st["quiet_ticks"].get(r, 0)
                    if qt > 0:
                        arrival = 0
                        st["quiet_ticks"][r] = qt - 1
                    else:
                        if random.random() < max(0.05, 0.35 - 0.25 * mult):
                            st["quiet_ticks"][r] = random.randint(2, 6)
                            arrival = 0
                        else:
                            arrival = random.randint(1, max(3, round(8 * mult)))
                    if is_green:
                        departure = random.randint(3, min(8, max(4, v // 6 + 3)))
                        delta = arrival - departure
                    else:
                        delta = arrival
                    st["road_vehicles"][r] = max(0, v + delta)
                _apply_junction_threshold(st)
                continue

            # ── Priority 2: VIP convoy override ───────────────────────────────
            # ALL signals at this junction → RED.  No departures.  Vehicles queue.
            vip = junction_vip.get(jid)
            if vip:
                toward = vip.get("green_toward")
                if toward and toward in roads:
                    st["active_idx"] = roads.index(toward)
                # Force RED on every tick — all approaches stopped
                st["phase"]          = "red"
                st["countdown"]      = 1
                st["green_duration"] = 1
                st["zero_since"]     = None

                if "quiet_ticks" not in st:
                    st["quiet_ticks"] = {r: 0 for r in roads}
                for r in roads:
                    v  = st["road_vehicles"][r]
                    qt = st["quiet_ticks"].get(r, 0)
                    if qt > 0:
                        arrival = 0
                        st["quiet_ticks"][r] = qt - 1
                    else:
                        if random.random() < max(0.05, 0.35 - 0.25 * mult):
                            st["quiet_ticks"][r] = random.randint(2, 6)
                            arrival = 0
                        else:
                            arrival = random.randint(1, max(3, round(8 * mult)))
                    st["road_vehicles"][r] = max(0, v + arrival)
                _apply_junction_threshold(st)
                continue

            # ── Priority 3: Upstream feeder block ─────────────────────────────
            # This junction feeds traffic INTO a corridor junction.
            # Force ALL signals RED — no vehicles may leave toward the corridor.
            # Signal stays RED; vehicle counts accumulate naturally.
            upstream = junction_upstream.get(jid)
            if upstream:
                st["phase"]          = "red"
                st["countdown"]      = 1
                st["green_duration"] = 1
                st["zero_since"]     = None

                if "quiet_ticks" not in st:
                    st["quiet_ticks"] = {r: 0 for r in roads}
                for r in roads:
                    v  = st["road_vehicles"][r]
                    qt = st["quiet_ticks"].get(r, 0)
                    if qt > 0:
                        arrival = 0
                        st["quiet_ticks"][r] = qt - 1
                    else:
                        if random.random() < max(0.05, 0.35 - 0.25 * mult):
                            st["quiet_ticks"][r] = random.randint(2, 6)
                            arrival = 0
                        else:
                            arrival = random.randint(1, max(3, round(8 * mult)))
                    st["road_vehicles"][r] = max(0, v + arrival)
                _apply_junction_threshold(st)
                continue

            # ── Normal adaptive signal logic ───────────────────────────────────
            active_road = roads[st["active_idx"]]

            if "quiet_ticks" not in st:
                st["quiet_ticks"] = {r: 0 for r in roads}

            # Hardware junctions: arrivals come from real IR sensors via
            # /api/sensor_update; skip software random arrival generation.
            # Departures still apply normally on green.
            is_hw = jid in HARDWARE_JUNCTIONS

            # Jam simulation: freeze vehicle counts for rupali_canal while active
            is_jam = (jid == "rupali_canal" and _rupali_jam_active)

            for r in roads:
                v         = st["road_vehicles"][r]
                is_green  = (r == active_road and st["phase"] == "green")
                is_yellow = (r == active_road and st["phase"] == "yellow")

                if is_jam:
                    # Jam active: keep counts at jam level — arrivals are locked in
                    # Re-pin the jam value every tick so departures can't drain it
                    st["road_vehicles"][r] = RUPALI_JAM_VEHICLES
                    continue

                if is_hw:
                    # Hardware junction: vehicle counts come EXCLUSIVELY from
                    # Arduino IR sensors via /api/sensor_set (VEH: messages).
                    # The simulation loop must NOT touch them — not arrivals,
                    # not departures. The physical sensors are the only truth.
                    pass
                else:
                    # Software simulation: bursty random arrivals
                    qt = st["quiet_ticks"].get(r, 0)
                    if qt > 0:
                        arrival = 0
                        st["quiet_ticks"][r] = qt - 1
                    else:
                        if random.random() < max(0.05, 0.35 - 0.25 * mult):
                            st["quiet_ticks"][r] = random.randint(2, 6)
                            arrival = 0
                        else:
                            arrival = random.randint(1, max(3, round(8 * mult)))

                    if is_green:
                        departure = random.randint(3, min(8, max(4, v // 6 + 3)))
                        delta = arrival - departure
                    elif is_yellow:
                        departure = random.randint(1, 3)
                        delta = arrival - departure
                    else:
                        delta = arrival

                    st["road_vehicles"][r] = max(0, v + delta)

            # ── Jam simulation: skip threshold cap so counts stay at forced level ──
            if is_jam:
                # Don't cap — the whole point is extreme congestion
                pass
            else:
                _apply_junction_threshold(st)  # cap total vehicles at JUNCTION_VEHICLE_THRESHOLD

            # ── Neighbor junctions choked during jam ─────────────────────────────
            is_jam_nbr = (_rupali_jam_active and jid in RUPALI_JAM_NEIGHBORS)
            if is_jam_nbr:
                for r in st["road_vehicles"]:
                    st["road_vehicles"][r] = RUPALI_JAM_NBR_VEHICLES


            # Zero-vehicle early skip
            # If the active road has 0 vehicles, skip the remaining green time
            # after a brief MIN_ELAPSED_BEFORE_SKIP guard (avoids single-tick flicker).
            # NOTE: the old MIN_GREEN guard has been removed — there is no reason
            # to wait 18 s when there are literally 0 vehicles queuing.
            MIN_ELAPSED_BEFORE_SKIP = 3   # seconds; prevents instant skip on first tick
            active_veh    = st["road_vehicles"][active_road]
            green_elapsed = st.get("green_duration", MIN_GREEN) - st["countdown"]
            if st["phase"] == "green" and active_veh == 0 and green_elapsed >= MIN_ELAPSED_BEFORE_SKIP:
                if st.get("zero_since") is None:
                    st["zero_since"] = ZERO_BLINK_SECS
                else:
                    st["zero_since"] -= 1
                    if st["zero_since"] <= 0:
                        st["phase"]      = "yellow"
                        st["countdown"]  = YELLOW_DURATION
                        st["zero_since"] = None
                        continue
            else:
                if active_veh > 0 or green_elapsed < MIN_ELAPSED_BEFORE_SKIP:
                    st["zero_since"] = None

            st["countdown"] -= 1
            if st["countdown"] > 0:
                continue

            if st["phase"] == "green":
                st["phase"]     = "yellow"
                st["countdown"] = YELLOW_DURATION
            else:
                next_idx  = (st["active_idx"] + 1) % len(roads)
                st["active_idx"] = next_idx
                next_road = roads[next_idx]
                veh       = st["road_vehicles"][next_road]
                green_dur = compute_green_time(veh, hour)
                # Apply any ML proactive bonus for this road (capped at MAX_GREEN)
                bonus     = st.pop("proactive_bonus", 0)
                green_dur = min(green_dur + bonus, MAX_GREEN)
                st["phase"]          = "green"
                st["countdown"]      = green_dur
                st["green_duration"] = green_dur
                st["zero_since"]     = None

        # ── ML predictive signal adjustment ─────────────────────────
        # Call predictor every tick to update rolling history and get
        # proactive green-time adjustments for roads about to congest.
        try:
            adjustments = predictor.tick(junction_state, hour, mult)
            for jid_adj, adj in adjustments.items():
                st_adj = junction_state.get(jid_adj)
                if not st_adj or jid_adj in junction_ambulance or jid_adj in junction_vip:
                    continue   # never override ambulance/VIP
                road_adj = adj["road"]
                roads_adj = st_adj["roads"]
                if road_adj not in roads_adj:
                    continue
                road_idx = roads_adj.index(road_adj)
                # Proactive: if this road will be the NEXT active road,
                # pre-extend its upcoming green duration
                next_idx = (st_adj["active_idx"] + 1) % len(roads_adj)
                if road_idx == next_idx and st_adj["phase"] in ("green", "yellow"):
                    # Store the bonus — applied when this road goes green
                    st_adj["proactive_bonus"] = st_adj.get("proactive_bonus", 0) + adj["extra_green_secs"]
                    st_adj["proactive_bonus"] = min(st_adj["proactive_bonus"], 20)  # cap at 20s extra
        except Exception:
            pass   # predictor errors must never crash the simulation

        time.sleep(1)


threading.Thread(target=update_traffic, daemon=True).start()


# ── API helpers ───────────────────────────────────────────────────────────────
def _congestion_level(vehicles):
    if vehicles < 20: return "low"
    if vehicles < 60: return "medium"
    return "high"


def _current_weights():
    weights = {}
    JAM_JID = "rupali_canal"
    for jid, st in junction_state.items():
        if not st["roads"]:
            weights[jid] = 0
            continue
        avg_veh = round(sum(st["road_vehicles"].values()) / len(st["roads"]))

        # Jam simulation: inject a huge Dijkstra penalty so the algorithm
        # strongly avoids Rupali Canal and its neighbors during the demo.
        if _rupali_jam_active:
            if jid == JAM_JID:
                avg_veh = 999   # effectively infinite cost — Dijkstra avoids at all costs
            elif jid in RUPALI_JAM_NEIGHBORS:
                avg_veh = max(avg_veh, 300)   # very heavy penalty on neighboring junctions

        # Red-signal penalty: vehicles at a red junction can't move, so
        # effective congestion is higher than the raw count suggests.
        # Add up to 30 phantom vehicles proportional to remaining red time.
        # This makes Dijkstra prefer paths whose NEXT junction is green.
        if st["phase"] == "red" and jid not in junction_ambulance:
            penalty = min(30, st["countdown"] // 2)
            avg_veh += penalty

        weights[jid] = avg_veh
    return weights


def _build_api(jid):
    j     = JUNCTIONS[jid]
    st    = junction_state[jid]
    roads = st["roads"]

    avg_vehicles = round(sum(st["road_vehicles"].values()) / len(roads)) if roads else 0

    # Determine overrides
    amb      = junction_ambulance.get(jid)
    vip      = junction_vip.get(jid)
    upstream = junction_upstream.get(jid)

    road_signals = []
    for idx, nb in enumerate(roads):
        is_active = (idx == st["active_idx"])
        vehicles  = st["road_vehicles"][nb]

        if vip or upstream:
            # ALL signals RED for VIP lockdown or upstream feeder block
            sig_phase     = "red"
            sig_countdown = 0
        elif amb and is_active:
            sig_phase     = "green"
            sig_countdown = max(0, st["countdown"])
        elif is_active and not amb:
            sig_phase     = st["phase"]
            sig_countdown = max(0, st["countdown"])
        else:
            sig_phase     = "red"
            sig_countdown = 0

        road_signals.append({
            "road_to":      nb,
            "road_to_name": JUNCTIONS[nb]["name"] if nb in JUNCTIONS else nb,
            "vehicles":     vehicles,
            "phase":        sig_phase,
            "countdown":    sig_countdown,
            "congestion":   _congestion_level(vehicles),
        })

    is_blinking = st["phase"] == "green" and st.get("zero_since") is not None

    return {
        "name":             j["name"],
        "lat":              j["lat"],
        "lng":              j["lng"],
        "vehicles":         avg_vehicles,
        "phase":            st["phase"],
        "countdown":        max(1, st["countdown"]),
        "congestion":       _congestion_level(avg_vehicles),
        "road_signals":     road_signals,
        "road_count":       len(roads),
        "blinking":         is_blinking,
        # Corridor flags for frontend rendering
        "ambulance":        bool(amb),
        "amb_toward":       amb["green_toward"] if amb else None,
        "vip":              bool(vip),
        "upstream_blocked": bool(upstream),
        "upstream_toward":  upstream["toward_jid"] if upstream else None,
        "upstream_type":    upstream["type"] if upstream else None,
        # Hardware flag — shown as badge in sidebar
        "hardware":         jid in HARDWARE_JUNCTIONS,
        "prediction":       predictor.get_junction_prediction(jid),
    }


def _interpolate_position(rec, move_interval):
    """Return (lat, lng, frac) interpolated between current and next junction."""
    path    = rec["path"]
    pos     = rec["position_idx"]
    cur_j   = JUNCTIONS.get(path[pos], {})
    if pos < len(path) - 1:
        next_j = JUNCTIONS.get(path[pos + 1], {})
        frac   = min(1.0, (time.time() - rec["last_moved"]) / move_interval)
        lat    = cur_j.get("lat", 0) + frac * (next_j.get("lat", 0) - cur_j.get("lat", 0))
        lng    = cur_j.get("lng", 0) + frac * (next_j.get("lng", 0) - cur_j.get("lng", 0))
    else:
        lat, lng, frac = cur_j.get("lat", 0), cur_j.get("lng", 0), 1.0
    return lat, lng, frac


# ── ETA calculator ─────────────────────────────────────────────────────────────
def _calculate_eta_comparison(src, dst):
    """
    Returns dict with normal_time, corridor_time, time_saved_pct, distance_km.
    Normal time  = shortest path with current live traffic weights (30 km/h base).
    Corridor time = physical distance at AMB_SPEED_CORRIDOR (50 km/h, no congestion).
    """
    weights = _current_weights()
    _, normal_dist, normal_time = graph.shortest_path(src, dst, weights)

    zero_weights = {jid: 0 for jid in JUNCTIONS}
    _, corridor_dist, _ = graph.shortest_path(src, dst, zero_weights)
    corridor_time = (corridor_dist / AMB_SPEED_CORRIDOR) * 60.0   # minutes at 50 km/h

    saved_pct = 0
    if normal_time > 0:
        saved_pct = max(0, round((normal_time - corridor_time) / normal_time * 100))

    return {
        "normal_time":    round(normal_time, 1),
        "corridor_time":  round(corridor_time, 1),
        "time_saved_pct": saved_pct,
        "distance_km":    round(corridor_dist, 2),
    }


# ── Flask routes ───────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", junctions=JUNCTIONS)


@app.route("/api/state")
def api_state():
    return jsonify({jid: _build_api(jid) for jid in JUNCTIONS})


@app.route("/api/route")
def api_route():
    src = request.args.get("from")
    dst = request.args.get("to")
    if not src or not dst or src not in JUNCTIONS or dst not in JUNCTIONS:
        return jsonify({"error": "Invalid junctions"}), 400

    weights = _current_weights()
    path, total_dist, total_time = graph.shortest_path(src, dst, weights)
    if not path:
        return jsonify({"error": "No path found"}), 404

    return jsonify({
        "path": [{"id": jid, "name": JUNCTIONS[jid]["name"],
                  "lat": JUNCTIONS[jid]["lat"], "lng": JUNCTIONS[jid]["lng"],
                  "vehicles": weights[jid]} for jid in path],
        "distance_km":       round(total_dist, 2),
        "estimated_minutes": round(total_time, 1),
        "path_ids":          path,          # plain list for quick comparison
    })


@app.route("/api/junctions")
def api_junctions():
    return jsonify(JUNCTIONS)


# ── Hardware Sensor Integration ────────────────────────────────────────────────
# rupali_canal_bridge.py posts real IR counts here every second.
# We ADD the new edge-counts to the existing queue, then re-calibrate
# the active green duration to match the real vehicle load.
# The junction is flagged as HARDWARE_JUNCTIONS so random arrivals are skipped.
#
# Works with ALL other features: ambulance corridors, VIP, upstream blocking,
# and ETA — the hardware junction participates in all of them normally.
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/sensor_update", methods=["POST"])
def api_sensor_update():
    """
    POST { "junction_id": "rupali_canal", "road_vehicles": [n0, n1, n2, n3] }

    road_vehicles[i] = cars detected since last call (IR edge counts).
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    jid        = data.get("junction_id")
    raw_counts = data.get("road_vehicles", [])

    if not jid or jid not in JUNCTIONS:
        return jsonify({"error": f"Unknown junction: {jid}"}), 404
    if jid not in junction_state:
        return jsonify({"error": "Junction not initialised yet"}), 503

    # Mark as hardware-driven — disables random arrival simulation
    HARDWARE_JUNCTIONS.add(jid)

    st    = junction_state[jid]
    roads = st["roads"]
    hour  = time.localtime().tm_hour

    # Inject real IR edge-counts into road queues
    for i, road in enumerate(roads):
        if i < len(raw_counts):
            new_cars = max(0, int(raw_counts[i]))
            st["road_vehicles"][road] = st["road_vehicles"].get(road, 0) + new_cars

    # If currently green, re-calibrate remaining green time for the active road
    # (only extend; never shorten below what's already elapsed)
    active_road = roads[st["active_idx"]] if roads else None
    if active_road and st["phase"] == "green":
        veh       = st["road_vehicles"].get(active_road, 0)
        new_green = compute_green_time(veh, hour)
        if new_green > st["countdown"]:
            st["countdown"]      = new_green
            st["green_duration"] = new_green

    return jsonify({
        "status":    "ok",
        "junction":  jid,
        "vehicles":  {road: st["road_vehicles"].get(road, 0) for road in roads},
        "phase":     st["phase"],
        "countdown": st["countdown"],
        "hardware":  True,
    })


@app.route("/api/hardware_connect", methods=["POST"])
def api_hardware_connect():
    """
    Called ONCE by the bridge immediately after serial connection is established.
    Zeros all vehicle counts for the junction so the dashboard starts from
    a clean slate — hardware IR sensors are now the single source of truth.
    Also marks the junction as HARDWARE so software random arrivals stop.

    POST { "junction_id": "rupali_canal" }
    """
    data = request.get_json(force=True, silent=True) or {}
    jid  = data.get("junction_id", "rupali_canal")

    if jid not in JUNCTIONS:
        return jsonify({"error": f"Unknown junction: {jid}"}), 404
    if jid not in junction_state:
        return jsonify({"error": "Junction not initialised yet"}), 503

    st    = junction_state[jid]
    roads = st["roads"]

    # Zero every road — hardware is now in charge
    for road in roads:
        st["road_vehicles"][road] = 0

    # Reset signal to safe initial state
    st["phase"]      = "red"
    st["countdown"]  = 5
    st["zero_since"] = None

    # Mark as hardware — disables random software arrivals
    HARDWARE_JUNCTIONS.add(jid)

    print(f"[HW CONNECT] {jid} — all vehicle counts zeroed, software sim disabled")

    return jsonify({
        "status":   "connected",
        "junction": jid,
        "message":  "Vehicle counts zeroed. Hardware IR sensors are now the source of truth.",
        "roads":    roads,
    })


@app.route("/api/sensor_set", methods=["POST"])
def api_sensor_set():
    """
    POST { "junction_id": "rupali_canal",
           "road_vehicles": [n0, n1, n2, n3],
           "active_dir": 0-3,
           "phase": "green"/"yellow"/"red",
           "countdown": seconds }

    Directly sets absolute vehicle counts from hardware (not deltas).
    Also syncs active signal phase so dashboard matches Arduino exactly.
    Called by rupali_canal_bridge.py every 500ms from VEH: messages.
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    jid = data.get("junction_id")
    if not jid or jid not in JUNCTIONS:
        return jsonify({"error": f"Unknown junction: {jid}"}), 404
    if jid not in junction_state:
        return jsonify({"error": "Junction not initialised yet"}), 503

    HARDWARE_JUNCTIONS.add(jid)

    st    = junction_state[jid]
    roads = st["roads"]
    hour  = time.localtime().tm_hour

    # --- Absolute vehicle counts (ground truth from Arduino IR sensors) ---
    raw_counts = data.get("road_vehicles", [])
    for i, road in enumerate(roads):
        if i < len(raw_counts):
            clamped = max(0, min(JUNCTION_VEHICLE_THRESHOLD, int(raw_counts[i])))
            st["road_vehicles"][road] = clamped

    # --- Sync signal phase from Arduino so dashboard matches hardware ---
    active_dir = data.get("active_dir")        # 0-3 integer
    hw_phase   = data.get("phase", "")         # "green"/"yellow"/"red"
    hw_countdown = data.get("countdown", None) # seconds remaining

    if active_dir is not None and 0 <= active_dir < len(roads):
        st["active_idx"] = active_dir

    if hw_phase in ("green", "yellow", "red"):
        st["phase"] = hw_phase

    # FIX: countdown is no longer sent by the bridge — always compute adaptively.
    # If the bridge (or a future caller) does send it, respect it as an override.
    if hw_countdown is not None:
        st["countdown"] = max(1, int(hw_countdown))
    else:
        # No countdown supplied — recalculate from vehicle count every call.
        active_road = roads[st["active_idx"]] if roads else None
        if hw_phase == "green" and active_road:
            # ML-adaptive green time based on real IR vehicle count
            veh = st["road_vehicles"].get(active_road, 0)
            new_green = compute_green_time(veh, hour)
            # Only update if it differs meaningfully (avoid constant resets resetting timer)
            if abs(new_green - st.get("countdown", 0)) > 2:
                st["countdown"]      = new_green
                st["green_duration"] = new_green
        elif hw_phase == "yellow":
            # Yellow is always a fixed short duration
            if st.get("phase") != "yellow":   # only reset when entering yellow
                st["countdown"] = YELLOW_DURATION

    st["zero_since"] = None  # reset blink state when hardware syncs

    return jsonify({
        "status":    "ok",
        "junction":  jid,
        "vehicles":  {road: st["road_vehicles"].get(road, 0) for road in roads},
        "phase":     st["phase"],
        "countdown": st["countdown"],
        "active_idx": st["active_idx"],
        "hardware":  True,
    })


@app.route("/api/hardware_status")
def api_hardware_status():
    """Returns which junctions are currently driven by real hardware."""
    return jsonify({
        "hardware_junctions": list(HARDWARE_JUNCTIONS),
        "total_junctions":    len(JUNCTIONS),
    })



@app.route("/api/route/check", methods=["POST"])
def api_route_check():
    """
    Smart rerouting check — called by the frontend every few seconds.

    Request body:
    {
      "from":             "<current_junction_id>",   // vehicle's current junction
      "to":               "<destination_id>",
      "committed_path":   ["jid1","jid2",...],       // full original path IDs
      "committed_ahead":  2                          // junctions ahead vehicle is committed to
    }

    Logic:
    1. Compute optimal route from `from` → `to` using live traffic weights
    2. Compare with `committed_path[vehicle_position:]`
    3. Detect critical bottleneck junctions AHEAD on the current path
    4. Reroute if:
       a. Path diverges beyond committed window
       b. The new path saves >= REROUTE_SAVING_THRESHOLD% congestion, OR
          a critical bottleneck (>= CRITICAL_VEH threshold) is found ahead
          on current path and new path avoids it (lower threshold applies)

    Returns:
    { "reroute": false }   — stay on current path
    { "reroute": true, "path": [...], "reason": "...", "ahead_traffic": [...] }
    """
    REROUTE_SAVING_THRESHOLD = 10    # % congestion reduction required normally
    CRITICAL_SAVING_THRESHOLD = 5   # % reduction sufficient when a bottleneck is critical
    CRITICAL_VEH = 80               # vehicles at a junction = critically congested
    LOOKAHEAD_JUNCTIONS = 5         # how many junctions ahead to scan for bottlenecks

    data = request.get_json(silent=True) or {}
    src            = data.get("from")
    dst            = data.get("to")
    committed_path = data.get("committed_path", [])
    committed_ahead = int(data.get("committed_ahead", 2))

    if not src or not dst or src not in JUNCTIONS or dst not in JUNCTIONS:
        return jsonify({"error": "Invalid junctions"}), 400

    weights = _current_weights()

    # ── Scan ahead on old path for critical bottlenecks ───────────────────────
    # Look at the next LOOKAHEAD_JUNCTIONS junctions beyond committed_ahead
    scan_window = committed_path[committed_ahead : committed_ahead + LOOKAHEAD_JUNCTIONS]
    ahead_traffic = []
    critical_bottleneck = None
    for jid in scan_window:
        if jid not in JUNCTIONS:
            continue
        veh = weights.get(jid, 0)
        cong_level = "low" if veh < 20 else "medium" if veh < 60 else "high"
        is_critical = (veh >= CRITICAL_VEH)
        ahead_traffic.append({
            "id":       jid,
            "name":     JUNCTIONS[jid]["name"],
            "vehicles": veh,
            "congestion": cong_level,
            "critical": is_critical,
        })
        if is_critical and critical_bottleneck is None:
            critical_bottleneck = {"id": jid, "name": JUNCTIONS[jid]["name"], "vehicles": veh}

    # ── Compute optimal route from vehicle's current position ─────────────────
    new_path, new_dist, new_time = graph.shortest_path(src, dst, weights)
    if not new_path:
        return jsonify({
            "reroute": False,
            "reason": "no_alt_path",
            "ahead_traffic": ahead_traffic,
        })

    old_remaining = committed_path  # already trimmed by frontend to remaining junctions

    if not old_remaining or len(old_remaining) < 2:
        return jsonify({"reroute": False, "reason": "near_destination", "ahead_traffic": ahead_traffic})

    # ── Check if path diverges beyond committed window ────────────────────────
    diverges_at = -1
    max_len = max(len(new_path), len(old_remaining))
    for i in range(max_len):
        if i < committed_ahead:
            continue
        if i >= len(old_remaining) or i >= len(new_path):
            diverges_at = i
            break
        if new_path[i] != old_remaining[i]:
            diverges_at = i
            break

    if diverges_at < 0:
        # Same path — but still report ahead traffic so frontend can warn user
        return jsonify({
            "reroute": False,
            "reason": "same_path",
            "ahead_traffic": ahead_traffic,
            "critical_ahead": critical_bottleneck,
        })

    # ── Calculate congestion cost comparison ──────────────────────────────────
    old_segment = old_remaining[committed_ahead:]
    new_segment = new_path[committed_ahead:]

    def avg_congestion(jid_list):
        if not jid_list:
            return 0
        return sum(weights.get(j, 0) for j in jid_list) / len(jid_list)

    old_cost = avg_congestion(old_segment)
    new_cost = avg_congestion(new_segment)

    if old_cost <= 0:
        saving_pct = 0
    else:
        saving_pct = (old_cost - new_cost) / old_cost * 100

    # ── Determine if reroute is warranted ─────────────────────────────────────
    # Use a lower threshold when there is a critical bottleneck ahead on old path
    # AND the new path avoids that bottleneck
    bottleneck_jid  = max(old_segment, key=lambda j: weights.get(j, 0), default=src)
    bottleneck_name = JUNCTIONS.get(bottleneck_jid, {}).get("name", bottleneck_jid)
    bottleneck_veh  = weights.get(bottleneck_jid, 0)

    has_critical_ahead = (critical_bottleneck is not None)
    new_path_avoids_bottleneck = (critical_bottleneck is not None and
                                  critical_bottleneck["id"] not in new_path)

    # Apply the appropriate threshold
    if has_critical_ahead and new_path_avoids_bottleneck:
        effective_threshold = CRITICAL_SAVING_THRESHOLD  # relaxed — bottleneck is critical
    else:
        effective_threshold = REROUTE_SAVING_THRESHOLD

    if saving_pct < effective_threshold:
        return jsonify({
            "reroute":        False,
            "reason":         "insufficient_saving",
            "saving_pct":     round(saving_pct, 1),
            "ahead_traffic":  ahead_traffic,
            "critical_ahead": critical_bottleneck,
        })

    # ── Build reason string ───────────────────────────────────────────────────
    if has_critical_ahead and new_path_avoids_bottleneck:
        reason = (f"Heavy congestion ahead at {critical_bottleneck['name']} "
                  f"({critical_bottleneck['vehicles']}v) — alternate route avoids it")
    else:
        reason = f"Congestion at {bottleneck_name} ({bottleneck_veh}v)"

    return jsonify({
        "reroute":           True,
        "path":              [{"id": jid, "name": JUNCTIONS[jid]["name"],
                               "lat": JUNCTIONS[jid]["lat"], "lng": JUNCTIONS[jid]["lng"],
                               "vehicles": weights[jid]} for jid in new_path],
        "path_ids":          new_path,
        "distance_km":       round(new_dist, 2),
        "estimated_minutes": round(new_time, 1),
        "reason":            reason,
        "bottleneck":        bottleneck_jid,
        "saving_pct":        round(saving_pct, 1),
        "old_cost":          round(old_cost, 1),
        "new_cost":          round(new_cost, 1),
        "ahead_traffic":     ahead_traffic,
        "critical_ahead":    critical_bottleneck,
    })


# ── Ambulance API ──────────────────────────────────────────────────────────────
@app.route("/api/ambulance", methods=["GET"])
def api_ambulance_list():
    result = []
    for rec in ambulance_corridors.values():
        lat, lng, frac = _interpolate_position(rec, AMB_MOVE_INTERVAL)
        pos = rec["position_idx"]
        path = rec["path"]
        entry = dict(rec)
        entry.update({
            "amb_lat": lat, "amb_lng": lng, "amb_frac": round(frac, 3),
            "amb_at_jid":  path[pos],
            "amb_at_name": JUNCTIONS.get(path[pos], {}).get("name", path[pos]),
            "priority_jids": path[max(0, pos-1):min(pos+PRIORITY_AHEAD+1, len(path))],
            "upstream_jids": [jid for jid, blk in junction_upstream.items()
                              if blk["corridor_id"] == rec["id"]],
        })
        result.append(entry)
    return jsonify(result)


@app.route("/api/ambulance", methods=["POST"])
def api_ambulance_activate():
    data = request.get_json(silent=True) or {}
    src, dst = data.get("from"), data.get("to")
    if not src or not dst:
        return jsonify({"error": "Both 'from' and 'to' are required"}), 400
    if src not in JUNCTIONS or dst not in JUNCTIONS:
        return jsonify({"error": "Invalid junction ID"}), 400
    if src == dst:
        return jsonify({"error": "Source and destination must be different"}), 400

    cid, err = _activate_corridor(src, dst)
    if err:
        return jsonify({"error": err}), 404

    rec = ambulance_corridors[cid]
    eta = _calculate_eta_comparison(src, dst)
    lat, lng, _ = _interpolate_position(rec, AMB_MOVE_INTERVAL)
    return jsonify({
        "id":           cid,
        "path":         rec["path"],
        "path_len":     len(rec["path"]),
        "distance_km":  rec["distance_km"],
        "from_name":    rec["from_name"],
        "to_name":      rec["to_name"],
        "amb_lat":      lat,
        "amb_lng":      lng,
        "eta":          eta,              # ← ETA comparison included on activation
    }), 201


@app.route("/api/ambulance/<cid>", methods=["DELETE"])
def api_ambulance_clear(cid):
    if _clear_corridor(cid):
        return jsonify({"cleared": cid, "message": "Corridor deactivated"})
    return jsonify({"error": f"Corridor '{cid}' not found"}), 404


@app.route("/api/ambulance/eta")
def api_ambulance_eta():
    """Standalone ETA comparison endpoint (no corridor activation needed)."""
    src = request.args.get("from")
    dst = request.args.get("to")
    if not src or not dst or src not in JUNCTIONS or dst not in JUNCTIONS:
        return jsonify({"error": "Invalid junctions"}), 400
    return jsonify(_calculate_eta_comparison(src, dst))


# ── VIP API ────────────────────────────────────────────────────────────────────
@app.route("/api/vip", methods=["GET"])
def api_vip_list():
    result = []
    for rec in vip_corridors.values():
        lat, lng, frac = _interpolate_position(rec, VIP_MOVE_INTERVAL)
        pos  = rec["position_idx"]
        path = rec["path"]
        ws   = max(0, pos - 1)
        we   = min(pos + PRIORITY_AHEAD + 1, len(path))
        entry = dict(rec)
        entry.update({
            "vip_lat": lat, "vip_lng": lng, "vip_frac": round(frac, 3),
            "vip_at_jid":    path[pos],
            "vip_at_name":   JUNCTIONS.get(path[pos], {}).get("name", path[pos]),
            "priority_jids": path[ws:we],
            "upstream_jids": [jid for jid, blk in junction_upstream.items()
                              if blk["corridor_id"] == rec["id"]],
        })
        result.append(entry)
    return jsonify(result)


@app.route("/api/vip", methods=["POST"])
def api_vip_activate():
    data = request.get_json(silent=True) or {}
    src, dst = data.get("from"), data.get("to")
    if not src or not dst:
        return jsonify({"error": "Both 'from' and 'to' are required"}), 400
    if src not in JUNCTIONS or dst not in JUNCTIONS:
        return jsonify({"error": "Invalid junction ID"}), 400
    if src == dst:
        return jsonify({"error": "Source and destination must be different"}), 400

    cid, err = _activate_vip_corridor(src, dst)
    if err:
        return jsonify({"error": err}), 404

    rec = vip_corridors[cid]
    lat, lng, _ = _interpolate_position(rec, VIP_MOVE_INTERVAL)
    return jsonify({
        "id":          cid,
        "path":        rec["path"],
        "path_len":    len(rec["path"]),
        "distance_km": rec["distance_km"],
        "from_name":   rec["from_name"],
        "to_name":     rec["to_name"],
        "vip_lat":     lat,
        "vip_lng":     lng,
    }), 201


@app.route("/api/vip/<cid>", methods=["DELETE"])
def api_vip_clear(cid):
    if _clear_vip_corridor(cid):
        return jsonify({"cleared": cid, "message": "VIP corridor deactivated"})
    return jsonify({"error": f"VIP corridor '{cid}' not found"}), 404


# ── Traffic Jam Simulation (demo button) ──────────────────────────────────────
# Allows the dashboard to artificially spike Rupali Canal traffic for a live
# rerouting demonstration.  When active, the simulation loop stops overwriting
# the forced counts so the spike is stable while it is held.


@app.route("/api/simulate/rupali_jam", methods=["POST"])
def api_rupali_jam_start():
    """Spike Rupali Canal vehicle counts to simulate extreme congestion."""
    global _rupali_jam_active
    jid = "rupali_canal"
    if jid not in junction_state:
        return jsonify({"error": "Junction not initialised"}), 503

    with _rupali_jam_lock:
        _rupali_jam_active = True
        # Spike main junction
        st    = junction_state[jid]
        roads = st["roads"]
        for road in roads:
            st["road_vehicles"][road] = RUPALI_JAM_VEHICLES
        # Spike neighbouring junctions immediately too
        for nbr_jid in RUPALI_JAM_NEIGHBORS:
            if nbr_jid in junction_state:
                nbr_st = junction_state[nbr_jid]
                for r in nbr_st["road_vehicles"]:
                    nbr_st["road_vehicles"][r] = RUPALI_JAM_NBR_VEHICLES

    print(f"[JAM SIM] Rupali Canal spiked to {RUPALI_JAM_VEHICLES} veh/road + {len(RUPALI_JAM_NEIGHBORS)} neighbors at {RUPALI_JAM_NBR_VEHICLES}")
    return jsonify({
        "status":    "jam_active",
        "junction":  jid,
        "vehicles":  RUPALI_JAM_VEHICLES,
        "neighbors": RUPALI_JAM_NEIGHBORS,
        "roads":     list(junction_state[jid]["roads"]),
    })


@app.route("/api/simulate/rupali_jam", methods=["DELETE"])
def api_rupali_jam_cancel():
    """Normalise Rupali Canal vehicle counts back to regular simulation."""
    global _rupali_jam_active
    jid = "rupali_canal"
    if jid not in junction_state:
        return jsonify({"error": "Junction not initialised"}), 503

    with _rupali_jam_lock:
        _rupali_jam_active = False
        t    = time.localtime()
        mult = get_traffic_multiplier(t.tm_hour, t.tm_min, t.tm_wday >= 5)
        # Reset main junction
        st    = junction_state[jid]
        roads = st["roads"]
        for road in roads:
            st["road_vehicles"][road] = max(5, round(random.randint(15, 40) * mult))
        # Reset neighbour junctions
        for nbr_jid in RUPALI_JAM_NEIGHBORS:
            if nbr_jid in junction_state:
                nbr_st = junction_state[nbr_jid]
                for r in nbr_st["road_vehicles"]:
                    nbr_st["road_vehicles"][r] = max(5, round(random.randint(15, 40) * mult))

    print("[JAM SIM] Rupali Canal + neighbors traffic normalised")
    return jsonify({
        "status":    "jam_cleared",
        "junction":  jid,
        "neighbors": RUPALI_JAM_NEIGHBORS,
    })


@app.route("/api/simulate/rupali_jam", methods=["GET"])
def api_rupali_jam_status():
    """Returns whether the jam simulation is currently active."""
    return jsonify({"active": _rupali_jam_active})


if __name__ == "__main__":
    print("🚦 Surat Smart Traffic System starting...")
    print("   Dashboard: http://127.0.0.1:5000")
    app.run(debug=True, use_reloader=False)