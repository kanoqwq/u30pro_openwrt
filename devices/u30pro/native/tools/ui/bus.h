/* ubus and UCI of the screen UI (device build): the object "u30pro.panel" and the screen settings in /etc/config/u30pro_native_control.
 *
 *   status {}                       page, screen on/off, input and touch, lock, theme
 *   screen {"action": "on"|"off"}   switch the screen on or off
 *   command {"cmd": "..."}          one UI command: page N, sheet N, fn N, overlay K ARG, home, wake, toast TEXT, notice [TEXT], theme N
 *   feed {"data": {key: value}}     the data the feeder (u30pro-ui-feed) collects: cellular, Wi-Fi, SMS, ... (keys of feed_set())
 *   reload {}                       read the settings again (after the web interface or uci changed them)
 * Events: "u30pro.panel.request" with kick/sms_refresh, scoped sms_read
 * {id,slot}, or sms_close. Legacy sms_ack remains accepted by the feeder.
 * Settings, section "display": theme (index), sleep (seconds: 30 60 120 300 0), wake (single|double|key), lock (0|1), pin
 * ("<salt>:<sha256(salt + PIN)>"), pinlen, touch_flip_x, touch_flip_y, and the wallpaper and glass of wall.h: wp_dim, glass, glass_blur,
 * glass_tint, wp_live, wp_live_pages, and fast_panel (0|1: the panel's high refresh, panel_speed in platform.h).
 * The connection is served from the UI's own poll loop (no uloop); it is opened again when ubusd goes away. */
#include <libubox/blobmsg.h>
#include <libubus.h>
#include <uci.h>

static struct ubus_context *bus;
static struct blob_buf bus_b;
static long bus_retry;

/* ------------------------------------------------------------------ settings in UCI */
static void cfg_set(struct uci_context *c, struct uci_package **pkg, const char *opt, const char *val)
{
	char path[192];
	struct uci_ptr p;

	snprintf(path, sizeof path, "u30pro_native_control.display%s%s=%s", opt ? "." : "", opt ? opt : "", val);
	if (!uci_lookup_ptr(c, &p, path, true) && !uci_set(c, &p))
		*pkg = p.p;
}

static void settings_save(void)
{
	struct uci_context *c = uci_alloc_context();
	struct uci_package *pkg = NULL;
	char v[32];

	if (!c) return;
	cfg_set(c, &pkg, NULL, "display");
	snprintf(v, sizeof v, "%d", theme_idx);
	cfg_set(c, &pkg, "theme", v);
	snprintf(v, sizeof v, "%d", OFF_SECS[off_idx % NOFF]);
	cfg_set(c, &pkg, "sleep", v);
	cfg_set(c, &pkg, "wake", WAKE_KEYS[wake_idx % NWAKE]);
	cfg_set(c, &pkg, "lock", lock_on ? "1" : "0");
	cfg_set(c, &pkg, "pin", pin_hash);
	snprintf(v, sizeof v, "%d", pin_hash[0] ? pin_digits : 0);
	cfg_set(c, &pkg, "pinlen", v);
	snprintf(v, sizeof v, "%d", wp_dim);
	cfg_set(c, &pkg, "wp_dim", v);
	snprintf(v, sizeof v, "%d", glass_clear);
	cfg_set(c, &pkg, "glass", v);
	snprintf(v, sizeof v, "%d", glass_blur);
	cfg_set(c, &pkg, "glass_blur", v);
	snprintf(v, sizeof v, "%d", glass_tint);
	cfg_set(c, &pkg, "glass_tint", v);
	snprintf(v, sizeof v, "%d", wp_live);
	cfg_set(c, &pkg, "wp_live", v);
	if (wp_live_pages >= 0) {
		snprintf(v, sizeof v, "%d", wp_live_pages);
		cfg_set(c, &pkg, "wp_live_pages", v);
	}
	if (pkg) uci_commit(c, &pkg, false);
	uci_free_context(c);
}

static int pin_hash_ok(const char *s);

static void settings_load(void)
{
	struct uci_context *c = uci_alloc_context();
	struct uci_package *pkg = NULL;
	struct uci_section *s;
	const char *v;

	wake_idx = WAKE_KEY;
	lock_on = 0;
	pin_hash[0] = 0;
	pin_digits = 0;
	wp_dim = 30; glass_clear = 50; glass_blur = 50; glass_tint = 0; wp_live = 2; wp_live_pages = -1; fast_panel = 0;
	if (!c) return;
	if (!uci_load(c, "u30pro_native_control", &pkg) && (s = uci_lookup_section(c, pkg, "display"))) {
		if ((v = uci_lookup_option_string(c, s, "theme")) && atoi(v) >= 0 && atoi(v) < NTHEMES) theme_idx = atoi(v);
		if ((v = uci_lookup_option_string(c, s, "sleep")) && *v >= '0' && *v <= '9')
			for (int i = 0; i < NOFF; i++) if (OFF_SECS[i] == atoi(v)) off_idx = i;
		if ((v = uci_lookup_option_string(c, s, "lock"))) lock_on = !strcmp(v, "1");
		if ((v = uci_lookup_option_string(c, s, "pinlen"))) pin_digits = atoi(v) >= 4 && atoi(v) <= 6 ? atoi(v) : 0;
		if ((v = uci_lookup_option_string(c, s, "wake"))) for (int i = 0; i < NWAKE; i++) if (!strcmp(v, WAKE_KEYS[i])) wake_idx = i;
		if ((v = uci_lookup_option_string(c, s, "pin")) && pin_hash_ok(v)) snprintf(pin_hash, sizeof pin_hash, "%s", v);
		/* the touch axes, for a panel mounted the other way (the real one needs neither) */
		touch_flip_x = (v = uci_lookup_option_string(c, s, "touch_flip_x")) && !strcmp(v, "1");
		touch_flip_y = (v = uci_lookup_option_string(c, s, "touch_flip_y")) && !strcmp(v, "1");
		if ((v = uci_lookup_option_string(c, s, "wp_dim")) && atoi(v) >= 0 && atoi(v) <= 90) wp_dim = atoi(v);
		if ((v = uci_lookup_option_string(c, s, "glass")) && atoi(v) >= 0 && atoi(v) <= 100) glass_clear = atoi(v);
		if ((v = uci_lookup_option_string(c, s, "glass_blur")) && atoi(v) >= 0 && atoi(v) <= 100) glass_blur = atoi(v);
		if ((v = uci_lookup_option_string(c, s, "glass_tint")) && atoi(v) >= 0 && atoi(v) < NTINT) glass_tint = atoi(v);
		if ((v = uci_lookup_option_string(c, s, "wp_live")) && atoi(v) >= 0 && atoi(v) <= 2) wp_live = atoi(v);
		if ((v = uci_lookup_option_string(c, s, "wp_live_pages")) && *v >= '0' && *v <= '9' && atoi(v) <= LIVE_ALL) wp_live_pages = atoi(v);
		fast_panel = (v = uci_lookup_option_string(c, s, "fast_panel")) && !strcmp(v, "1");
	}
	key_short = KA_PAGE;
	key_long = KA_NONE;
	key_long_ms = 1800;
	if (pkg && (s = uci_lookup_section(c, pkg, "settings"))) {
		key_short = key_action_idx(uci_lookup_option_string(c, s, "home_short_action"), KA_PAGE);
		key_long = key_action_idx(uci_lookup_option_string(c, s, "home_long_action"), KA_NONE);
		if (key_long == KA_PAGE) key_long = KA_NONE;
		if ((v = uci_lookup_option_string(c, s, "home_long_press_ms")) && key_long_ms_ok(atoi(v))) key_long_ms = atoi(v);
	}
	uci_free_context(c);
	panel_speed(panel_fast_now > 0);	/* switched off: back to 48 MHz at once */
}

/* ------------------------------------------------------------------ requests to the feeder */
static void bus_request(const char *what)
{
	if (!bus) return;
	blob_buf_init(&bus_b, 0);
	blobmsg_add_string(&bus_b, "request", what);
	ubus_send_event(bus, "u30pro.panel.request", bus_b.head);
}

static void bus_sms_read(const char *id, int slot)
{
	if (!bus) return;
	blob_buf_init(&bus_b, 0);
	blobmsg_add_string(&bus_b, "request", "sms_read");
	blobmsg_add_string(&bus_b, "id", id);
	blobmsg_add_string(&bus_b, "slot", slot ? "1" : "0");
	ubus_send_event(bus, "u30pro.panel.request", bus_b.head);
}

static void incoming_replace(const IncomingCall *calls, int count);
static void bus_call_hangup(const char *id)
{
	if (!bus) return;
	blob_buf_init(&bus_b, 0);
	blobmsg_add_string(&bus_b, "request", "call_hangup");
	blobmsg_add_string(&bus_b, "id", id);
	ubus_send_event(bus, "u30pro.panel.request", bus_b.head);
}

enum { IC_CALLS, __IC_MAX };
static const struct blobmsg_policy incoming_policy[__IC_MAX] = {
	[IC_CALLS] = { "calls", BLOBMSG_TYPE_ARRAY }
};
enum { IC_ID, IC_NUMBER, IC_LABEL, __IC_ROW_MAX };
static const struct blobmsg_policy incoming_row_policy[__IC_ROW_MAX] = {
	[IC_ID] = { "id", BLOBMSG_TYPE_STRING }, [IC_NUMBER] = { "number", BLOBMSG_TYPE_STRING },
	[IC_LABEL] = { "label", BLOBMSG_TYPE_STRING }
};
static int m_incoming(struct ubus_context *c, struct ubus_object *o,
        struct ubus_request_data *req, const char *method, struct blob_attr *msg)
{
	struct blob_attr *tb[__IC_MAX], *row[__IC_ROW_MAX], *cur;
	IncomingCall calls[8] = {0};
	int count = 0;
	size_t rem;
	(void)c; (void)o; (void)req; (void)method;
	blobmsg_parse(incoming_policy, __IC_MAX, tb, blob_data(msg), blob_len(msg));
	if (!tb[IC_CALLS]) return UBUS_STATUS_INVALID_ARGUMENT;
	blobmsg_for_each_attr(cur, tb[IC_CALLS], rem) {
		if (count == 8 || blobmsg_type(cur) != BLOBMSG_TYPE_TABLE) return UBUS_STATUS_INVALID_ARGUMENT;
		blobmsg_parse(incoming_row_policy, __IC_ROW_MAX, row, blobmsg_data(cur), blobmsg_data_len(cur));
		if (!row[IC_ID] || !row[IC_NUMBER] || !row[IC_LABEL]) return UBUS_STATUS_INVALID_ARGUMENT;
		const char *id = blobmsg_get_string(row[IC_ID]), *number = blobmsg_get_string(row[IC_NUMBER]), *label = blobmsg_get_string(row[IC_LABEL]);
		if (strlen(id) != 32 || strspn(id, "0123456789abcdef") != 32 || strlen(number) >= sizeof calls[0].number ||
		    strspn(number, "+0123456789*#") != strlen(number) || strlen(label) >= sizeof calls[0].label || strpbrk(label, "\r\n\t"))
			return UBUS_STATUS_INVALID_ARGUMENT;
		for (int i = 0; i < count; i++) if (!strcmp(calls[i].id, id)) return UBUS_STATUS_INVALID_ARGUMENT;
		snprintf(calls[count].id, sizeof calls[count].id, "%s", id);
		snprintf(calls[count].number, sizeof calls[count].number, "%s", number);
		snprintf(calls[count].label, sizeof calls[count].label, "%s", label);
		count++;
	}
	incoming_replace(calls, count);
	return 0;
}

enum { IR_ID, IR_OK, __IR_MAX };
static const struct blobmsg_policy incoming_result_policy[__IR_MAX] = {
	[IR_ID] = { "id", BLOBMSG_TYPE_STRING }, [IR_OK] = { "ok", BLOBMSG_TYPE_BOOL }
};
static int m_incoming_result(struct ubus_context *c, struct ubus_object *o,
        struct ubus_request_data *req, const char *method, struct blob_attr *msg)
{
	struct blob_attr *tb[__IR_MAX];
	(void)c; (void)o; (void)req; (void)method;
	blobmsg_parse(incoming_result_policy, __IR_MAX, tb, blob_data(msg), blob_len(msg));
	if (!tb[IR_ID] || !tb[IR_OK]) return UBUS_STATUS_INVALID_ARGUMENT;
	const IncomingCall *v = incoming_visible();
	if (v && !strcmp(v->id, blobmsg_get_string(tb[IR_ID]))) {
		incoming_busy = 0;
		if (blobmsg_get_bool(tb[IR_OK])) {
			for (int i = 0; i < incoming_count; i++) if (!strcmp(incoming_calls[i].id, blobmsg_get_string(tb[IR_ID]))) incoming_calls[i].ignored = 1;
		} else toast_show("挂断失败，请重试", C_WARN, 3000);
		dirty = 1;
	}
	return 0;
}

/* ------------------------------------------------------------------ the object */
static void settings_apply(void);
static void ui_cmd_line(const char *line);

static int m_status(struct ubus_context *c, struct ubus_object *o, struct ubus_request_data *req, const char *method, struct blob_attr *msg)
{
	(void)o; (void)method; (void)msg;
	blob_buf_init(&bus_b, 0);
	blobmsg_add_u32(&bus_b, "page", (uint32_t)page);
	blobmsg_add_u8(&bus_b, "screen_on", !asleep);
	blobmsg_add_u8(&bus_b, "power_menu", power_menu);
	blobmsg_add_u32(&bus_b, "power_confirmation", power_choice);
	blobmsg_add_u32(&bus_b, "key_count", key_count);
	blobmsg_add_u32(&bus_b, "last_key", last_key);
	blobmsg_add_u8(&bus_b, "input_ready", keyfd >= 0);
	blobmsg_add_u32(&bus_b, "rotation", 180);
	blobmsg_add_u8(&bus_b, "round_safe", 1);
	blobmsg_add_u8(&bus_b, "touch_ready", touchfd >= 0);
	blobmsg_add_u32(&bus_b, "touch_count", touch_count);
	blobmsg_add_u32(&bus_b, "gesture_count", gesture_count);
	blobmsg_add_string(&bus_b, "last_gesture", last_gesture);
	blobmsg_add_string(&bus_b, "ui", "rich");
	blobmsg_add_u32(&bus_b, "theme", (uint32_t)theme_idx);
	blobmsg_add_u8(&bus_b, "locked", locked);
	blobmsg_add_u8(&bus_b, "feed_ok", D.feed_ok);
	blobmsg_add_u8(&bus_b, "power_events_ready", powerfd >= 0);
	blobmsg_add_u8(&bus_b, "external_power_known", power_known);
	blobmsg_add_u8(&bus_b, "external_power_online", power_online);
	ubus_send_reply(c, req, bus_b.head);
	return 0;
}

static void go_sleep(void);
static void wake(void);

enum { A_ACTION, __A_MAX };
static const struct blobmsg_policy screen_policy[__A_MAX] = { [A_ACTION] = { "action", BLOBMSG_TYPE_STRING } };

static int m_screen(struct ubus_context *c, struct ubus_object *o, struct ubus_request_data *req, const char *method, struct blob_attr *msg)
{
	struct blob_attr *tb[__A_MAX];
	const char *a;

	(void)c; (void)o; (void)req; (void)method;
	blobmsg_parse(screen_policy, __A_MAX, tb, blob_data(msg), blob_len(msg));
	a = tb[A_ACTION] ? blobmsg_get_string(tb[A_ACTION]) : "";
	if (!strcmp(a, "off")) go_sleep();
	else if (!strcmp(a, "on")) wake();
	else return UBUS_STATUS_INVALID_ARGUMENT;
	last_gesture = asleep ? "remote-sleep" : "remote-wake";
	return m_status(c, o, req, method, msg);
}

enum { C_CMD, __C_MAX };
static const struct blobmsg_policy command_policy[__C_MAX] = { [C_CMD] = { "cmd", BLOBMSG_TYPE_STRING } };

static int m_command(struct ubus_context *c, struct ubus_object *o, struct ubus_request_data *req, const char *method, struct blob_attr *msg)
{
	struct blob_attr *tb[__C_MAX];

	blobmsg_parse(command_policy, __C_MAX, tb, blob_data(msg), blob_len(msg));
	if (!tb[C_CMD]) return UBUS_STATUS_INVALID_ARGUMENT;
	ui_cmd_line(blobmsg_get_string(tb[C_CMD]));
	return m_status(c, o, req, method, msg);
}

enum { F_DATA, __F_MAX };
static const struct blobmsg_policy feed_policy[__F_MAX] = { [F_DATA] = { "data", BLOBMSG_TYPE_TABLE } };

static int m_feed(struct ubus_context *c, struct ubus_object *o, struct ubus_request_data *req, const char *method, struct blob_attr *msg)
{
	struct blob_attr *tb[__F_MAX], *cur;
	size_t rem;
	char v[1024];

	(void)c; (void)o; (void)req; (void)method;
	blobmsg_parse(feed_policy, __F_MAX, tb, blob_data(msg), blob_len(msg));
	if (!tb[F_DATA]) return UBUS_STATUS_INVALID_ARGUMENT;
	D.nsms = 0;
	for (int i = 0; i < 6; i++) D.sms[i].id[0] = 0;
	D.sinr_ok = D.nr = D.nr_idle = D.nr_rsrp_ok = D.nr_sinr_ok = 0;
	D.bw_idx = -1;
	D.lte_bw[0] = 0;
	D.nr_bw = 0;
	memset(D.cl, 0, sizeof D.cl);
	blobmsg_for_each_attr(cur, tb[F_DATA], rem) {
		switch (blobmsg_type(cur)) {
		case BLOBMSG_TYPE_STRING: snprintf(v, sizeof v, "%s", blobmsg_get_string(cur)); break;
		case BLOBMSG_TYPE_INT8: snprintf(v, sizeof v, "%d", blobmsg_get_bool(cur)); break;
		case BLOBMSG_TYPE_INT32: snprintf(v, sizeof v, "%d", (int)blobmsg_get_u32(cur)); break;
		case BLOBMSG_TYPE_INT64: snprintf(v, sizeof v, "%lld", (long long)blobmsg_get_u64(cur)); break;
		case BLOBMSG_TYPE_DOUBLE: snprintf(v, sizeof v, "%g", blobmsg_get_double(cur)); break;
		default: continue;
		}
		feed_set(blobmsg_name(cur), v);
		if (!strcmp(blobmsg_name(cur), "sms_error") && v[0]) toast_show(v, C_WARN, 2500);
	}
	D.feed_ok = 1;
	if (!asleep) dirty = 1;
	return 0;
}

static int m_reload(struct ubus_context *c, struct ubus_object *o, struct ubus_request_data *req, const char *method, struct blob_attr *msg)
{
	settings_apply();
	return m_status(c, o, req, method, msg);
}

/* A separate completion method must not clear cellular/SMS fields as feed does. */
enum { Q_TOKEN, Q_RESULT, __Q_MAX };
static const struct blobmsg_policy charge_policy[__Q_MAX] = {
	[Q_TOKEN] = { "token", BLOBMSG_TYPE_STRING }, [Q_RESULT] = { "result", BLOBMSG_TYPE_TABLE }
};
enum { CHGR_OK, CHGR_AVAILABLE, CHGR_PAUSED, CHGR_REASON, CHGR_PENDING, CHGR_ERROR, __CHGR_MAX };
static const struct blobmsg_policy charge_result_policy[__CHGR_MAX] = {
	[CHGR_OK] = { "ok", BLOBMSG_TYPE_BOOL }, [CHGR_AVAILABLE] = { "available", BLOBMSG_TYPE_BOOL },
	[CHGR_PAUSED] = { "paused", BLOBMSG_TYPE_BOOL }, [CHGR_REASON] = { "reason", BLOBMSG_TYPE_STRING },
	[CHGR_PENDING] = { "pending", BLOBMSG_TYPE_BOOL }, [CHGR_ERROR] = { "error", BLOBMSG_TYPE_STRING }
};
static int m_charge_result(struct ubus_context *c, struct ubus_object *o,
        struct ubus_request_data *req, const char *method, struct blob_attr *msg)
{
	struct blob_attr *tb[__Q_MAX], *r[__CHGR_MAX];
	(void)c; (void)o; (void)req; (void)method;
	blobmsg_parse(charge_policy, __Q_MAX, tb, blob_data(msg), blob_len(msg));
	if (!tb[Q_TOKEN] || !tb[Q_RESULT]) return UBUS_STATUS_INVALID_ARGUMENT;
	const char *token = blobmsg_get_string(tb[Q_TOKEN]);
	if (!token[0] || strspn(token, "0123456789") != strlen(token)) return UBUS_STATUS_INVALID_ARGUMENT;
	blobmsg_parse(charge_result_policy, __CHGR_MAX, r, blobmsg_data(tb[Q_RESULT]), blobmsg_data_len(tb[Q_RESULT]));
	int ok = r[CHGR_OK] && blobmsg_get_bool(r[CHGR_OK]);
	if (ok && (!r[CHGR_AVAILABLE] || !r[CHGR_PAUSED] || !r[CHGR_PENDING] || !r[CHGR_REASON])) return UBUS_STATUS_INVALID_ARGUMENT;
	bypass_complete((unsigned)strtoul(token, NULL, 10), ok,
	    r[CHGR_AVAILABLE] && blobmsg_get_bool(r[CHGR_AVAILABLE]), r[CHGR_PAUSED] && blobmsg_get_bool(r[CHGR_PAUSED]),
	    r[CHGR_REASON] && !strcmp(blobmsg_get_string(r[CHGR_REASON]), "limit"),
	    r[CHGR_PENDING] && blobmsg_get_bool(r[CHGR_PENDING]), r[CHGR_ERROR] ? blobmsg_get_string(r[CHGR_ERROR]) : "charge_failed");
	bus_request("kick");
	return 0;
}

enum { SIM_OK, SIM_TARGET, SIM_ERROR, __SIM_RESULT_MAX };
static const struct blobmsg_policy sim_result_policy[__SIM_RESULT_MAX] = {
    [SIM_OK] = {"ok", BLOBMSG_TYPE_BOOL}, [SIM_TARGET] = {"target", BLOBMSG_TYPE_INT32},
    [SIM_ERROR] = {"error", BLOBMSG_TYPE_STRING}
};
static int m_data_sim_result(struct ubus_context *c, struct ubus_object *o,
    struct ubus_request_data *req, const char *method, struct blob_attr *msg)
{
    struct blob_attr *tb[__Q_MAX], *r[__SIM_RESULT_MAX];
    blobmsg_parse(charge_policy, __Q_MAX, tb, blob_data(msg), blob_len(msg));
    if (!tb[Q_TOKEN] || !tb[Q_RESULT]) return UBUS_STATUS_INVALID_ARGUMENT;
    const char *token = blobmsg_get_string(tb[Q_TOKEN]);
    if (!token[0] || strlen(token) > 10 || strspn(token, "0123456789") != strlen(token)) return UBUS_STATUS_INVALID_ARGUMENT;
    blobmsg_parse(sim_result_policy, __SIM_RESULT_MAX, r, blobmsg_data(tb[Q_RESULT]), blobmsg_data_len(tb[Q_RESULT]));
    if (!r[SIM_OK] || !r[SIM_TARGET]) return UBUS_STATUS_INVALID_ARGUMENT;
    data_sim_complete((unsigned)strtoul(token, NULL, 10), blobmsg_get_u32(r[SIM_TARGET]),
        blobmsg_get_bool(r[SIM_OK]), r[SIM_ERROR] ? blobmsg_get_string(r[SIM_ERROR]) : "");
    return 0;
}

static const struct ubus_method bus_methods[] = {
	UBUS_METHOD_NOARG("status", m_status),
	UBUS_METHOD("screen", m_screen, screen_policy),
	UBUS_METHOD("command", m_command, command_policy),
	UBUS_METHOD("feed", m_feed, feed_policy),
	UBUS_METHOD("charge_result", m_charge_result, charge_policy),
	UBUS_METHOD("data_sim_result", m_data_sim_result, charge_policy),
	UBUS_METHOD("incoming", m_incoming, incoming_policy),
	UBUS_METHOD("incoming_result", m_incoming_result, incoming_result_policy),
	UBUS_METHOD_NOARG("reload", m_reload),
};
static struct ubus_object_type bus_type = UBUS_OBJECT_TYPE("u30pro.panel", bus_methods);
static struct ubus_object bus_object = {
	.name = "u30pro.panel", .type = &bus_type, .methods = bus_methods, .n_methods = ARRAY_SIZE(bus_methods),
};

/* connect (again) when there is no connection; returns the descriptor to poll, -1 without a connection */
static int bus_fd(long now)
{
	if (bus && (bus->sock.eof || bus->sock.error)) {
		ubus_free(bus);
		bus = NULL;
	}
	if (!bus && now >= bus_retry) {
		bus_retry = now + 2000;
		bus = ubus_connect(NULL);
		if (bus && ubus_add_object(bus, &bus_object)) {
			ubus_free(bus);
			bus = NULL;
		}
		if (bus) { bus_request("kick"); bus_request("call_refresh"); }
	}
	return bus ? bus->sock.fd : -1;
}

static void bus_handle(void)
{
	if (bus) ubus_handle_event(bus);
}
