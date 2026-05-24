// Sample JS fragment mimicking 梦音's signature function
// Pattern: MD5_key_suffix — MD5(sorted_params + "&key=" + sign_key)

var CryptoJS = require("crypto-js");

// Parameters excluded from signing
var EXCLUDE_KEYS = [
    "pub_sign", "pub_uid", "pub_ticket", "appVersion", "appVersionCode",
    "channel", "deviceId", "ispType", "model", "netType", "os",
    "osVersion", "app", "ticket", "smDeviceId", "newDeviceId"
];

// Sign key: initially empty, later loaded from /login/h5/sign/token
var k = "";

// The sign function
function I(e, t) {
    var n = {};
    for (var r in e) {
        if (EXCLUDE_KEYS.indexOf(r) === -1 && e.hasOwnProperty(r)) {
            n[r] = e[r];
        }
    }
    n.pub_timestamp = t;
    var o = Object.keys(n).sort();
    var a = [];
    for (var i = 0; i < o.length; i++) {
        a.push(o[i] + "=" + n[o[i]]);
    }
    var s = a.join("&");
    return CryptoJS.MD5(s + "&key=" + k).toString().toUpperCase();
}

// Update sign key from API response
function updateKey(newKey) {
    k = newKey;
}

module.exports = { I: I, updateKey: updateKey };
