// 旧版 mCaptcha API 本地中转：手机网络无法直连 captchas.wanmei.com 时，
// 把组件的取图/校验 JSONP 请求重定向到本服务器，验证码仍需用户手动拖动。
(function () {
  if (!window.jQuery) return;
  window.__PROXY_LOG__ = window.__PROXY_LOG__ || [];
  var orig = jQuery.ajax;
  jQuery.ajax = function (s) {
    var u = s.url || "";
    var mKey = u.match(/captchas\.wanmei\.com\/mCaptcha\/(key|validate)(\?.*)?$/);
    var mInfo = u.match(/captchas\.wanmei\.com\/mCaptcha\/info\/([a-f0-9]+)/);
    var mAi = u.match(/captchas\.wanmei\.com\/aicaptcha\/getCaptcha/);
    if (mKey) {
      window.__PROXY_LOG__.push(mKey[1]);
      s.url = "/nte/scratch/mCaptchaProxy/" + mKey[1];
      s.data = jQuery.extend({}, s.data || {});
      s.data.auth = window.__NTE_AUTH__ || "";
      s.dataType = "json";
      s.type = "POST";
      s.contentType = "application/json";
      s.data = JSON.stringify(s.data);
    } else if (mInfo) {
      window.__PROXY_LOG__.push("info");
      s.url = "/nte/scratch/mCaptchaProxy/info";
      s.data = jQuery.extend({}, s.data || {});
      s.data.auth = window.__NTE_AUTH__ || "";
      s.data.capKey = mInfo[1];
      s.dataType = "json";
      s.type = "POST";
      s.contentType = "application/json";
      s.data = JSON.stringify(s.data);
    } else if (mAi) {
      // PC 版组件走 aicaptcha/getCaptcha，同样中转
      window.__PROXY_LOG__.push("aicaptcha");
      s.url = "/nte/scratch/mCaptchaProxy/key";
      s.data = jQuery.extend({}, s.data || {});
      s.data.auth = window.__NTE_AUTH__ || "";
      s.dataType = "json";
      s.type = "POST";
      s.contentType = "application/json";
      s.data = JSON.stringify(s.data);
    }
    return orig.call(this, s);
  };
})();
