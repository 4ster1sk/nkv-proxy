/* Misskey-Mastodon Proxy — common JS */
"use strict";

// フォーム送信中はボタンを無効化
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function () {
      form.querySelectorAll("button[type=submit]").forEach(function (btn) {
        btn.disabled = true;
        btn.textContent = "処理中...";
      });
    });
  });
});
