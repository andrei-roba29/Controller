/* PadLink relay: a tiny Supabase Realtime client.
 *
 * Deliberately dependency-free. The old version dynamically imported
 * supabase-js from a CDN; when a phone or a network blocks that CDN, the import
 * simply never resolves and "Connect" appears to do nothing. This speaks the
 * Phoenix websocket protocol directly (~150 lines) and reports every step, so
 * the page can show what is happening.
 */
(function (root) {
  "use strict";

  function normalize(url) {
    return String(url)
      .replace(/\/+$/, "")
      .replace(/^https:/, "wss:")
      .replace(/^http:/, "ws:");
  }

  function PadLinkRelay(opts) {
    this.base = normalize(opts.url);
    this.key = opts.key;
    this.room = opts.room;
    this.topic = "realtime:padlink:" + opts.room;
    this.onStatus = opts.onStatus || function () {};
    this.onSettings = opts.onSettings || function () {};
    this.onAlive = opts.onAlive || function () {};
    this.onError = opts.onError || function () {};

    this.ws = null;
    this.ref = 0;
    this.joinRef = null;
    this.joined = false;
    this.closed = false;
    this.backoff = 1;
    this.heartbeat = null;
    this.retry = null;
  }

  PadLinkRelay.prototype.connect = function () {
    var self = this;
    this.closed = false;
    this.onStatus("connecting");

    var url = this.base + "/realtime/v1/websocket?apikey=" +
      encodeURIComponent(this.key) + "&vsn=1.0.0";
    var ws;
    try {
      ws = new WebSocket(url);
    } catch (e) {
      this.onError("Could not open the relay connection.");
      return;
    }
    this.ws = ws;
    ws.onopen = function () { self.join(); };
    ws.onmessage = function (ev) { self.frame(ev.data); };
    ws.onerror = function () {};  /* onclose always follows */
    ws.onclose = function () {
      self.joined = false;
      self.stopHeartbeat();
      if (self.closed) { self.onStatus("closed"); return; }
      self.onStatus("reconnecting");
      self.scheduleRetry();
    };
  };

  PadLinkRelay.prototype.join = function () {
    this.onStatus("joining");
    var ref = String(++this.ref);
    this.joinRef = ref;
    this.send({
      topic: this.topic,
      event: "phx_join",
      ref: ref,
      join_ref: ref,
      payload: {
        config: {
          broadcast: {ack: false, self: false},
          presence: {key: ""},
          postgres_changes: [],
          private: true
        },
        access_token: this.key
      }
    });
  };

  PadLinkRelay.prototype.frame = function (data) {
    var msg;
    try { msg = JSON.parse(data); } catch (e) { return; }
    var event = msg.event, payload = msg.payload || {};

    if (event === "phx_reply" && msg.ref === this.joinRef) {
      if (payload.status === "ok") {
        this.joined = true;
        this.backoff = 1;
        this.startHeartbeat();
        this.onStatus("joined");
      } else {
        var response = payload.response || {};
        var reason = response.reason || response.message || payload.status;
        this.onError("The relay rejected this room (" + reason + ").");
      }
      return;
    }
    if (event === "broadcast") {
      if (payload.event === "pc-alive") this.onAlive();
      if (payload.event === "settings-response") this.onSettings(payload.payload || {});
      return;
    }
    if (event === "phx_error" || event === "phx_close") {
      this.joined = false;
      this.stopHeartbeat();
      this.onStatus("reconnecting");
      try { this.ws.close(); } catch (e) {}
      this.scheduleRetry();
    }
  };

  PadLinkRelay.prototype.send = function (frame) {
    if (!this.ws || this.ws.readyState !== 1) return false;
    this.ws.send(JSON.stringify(frame));
    return true;
  };

  /** Send the full input snapshot; ignored until the room is joined. */
  PadLinkRelay.prototype.input = function (state) {
    if (!this.joined) return;
    this.send({
      topic: this.topic,
      event: "broadcast",
      ref: String(++this.ref),
      join_ref: this.joinRef,
      payload: {type: "broadcast", event: "input", payload: state}
    });
  };

  PadLinkRelay.prototype.settings = function (request) {
    if (!this.joined) return false;
    return this.send({topic: this.topic, event: "broadcast", ref: String(++this.ref),
      join_ref: this.joinRef,
      payload: {type: "broadcast", event: "settings-request", payload: request}});
  };

  PadLinkRelay.prototype.startHeartbeat = function () {
    var self = this;
    this.stopHeartbeat();
    this.heartbeat = setInterval(function () {
      self.send({topic: "phoenix", event: "heartbeat", payload: {}, ref: String(++self.ref)});
    }, 25000);
  };

  PadLinkRelay.prototype.stopHeartbeat = function () {
    if (this.heartbeat) { clearInterval(this.heartbeat); this.heartbeat = null; }
  };

  PadLinkRelay.prototype.scheduleRetry = function () {
    var self = this;
    if (this.closed || this.retry) return;
    var wait = Math.min(8000, 500 * this.backoff++);
    this.retry = setTimeout(function () { self.retry = null; self.connect(); }, wait);
  };

  PadLinkRelay.prototype.close = function () {
    this.closed = true;
    this.stopHeartbeat();
    if (this.retry) { clearTimeout(this.retry); this.retry = null; }
    if (this.ws) { try { this.ws.close(); } catch (e) {} }
  };

  root.PadLinkRelay = PadLinkRelay;
})(typeof window !== "undefined" ? window : globalThis);
