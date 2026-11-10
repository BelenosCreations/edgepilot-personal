package com.edgepilot.mobile;

import android.app.Activity;
import android.content.Intent;
import android.content.ActivityNotFoundException;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.SslErrorHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import androidx.webkit.WebSettingsCompat;
import androidx.webkit.WebViewFeature;
import android.net.http.SslError;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.ByteArrayInputStream;

/** Private EdgePilot Android test shell. The backend and all trading logic run in Render. */
public final class MainActivity extends Activity {
    private static final String SITE = "https://edgepilot.belenoscreations.biz/";
    private static final String HOST = "edgepilot.belenoscreations.biz";
    private WebView webView;
    private View offlinePanel;
    private boolean pageFailed;

    private static boolean allowed(Uri uri) {
        return uri != null && "https".equalsIgnoreCase(uri.getScheme())
                && HOST.equalsIgnoreCase(uri.getHost())
                && (uri.getPort() == -1 || uri.getPort() == 443)
                && uri.getUserInfo() == null;
    }

    private static boolean approvedPublicHelp(Uri uri) {
        if (uri == null || !"https".equalsIgnoreCase(uri.getScheme())
                || !"public.com".equalsIgnoreCase(uri.getHost())
                || (uri.getPort() != -1 && uri.getPort() != 443)
                || uri.getUserInfo() != null || uri.getQuery() != null
                || uri.getFragment() != null) return false;
        final String path = uri.getPath();
        return "/signup".equals(path) || "/api/docs/quickstart".equals(path);
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(12,20,35));
        getWindow().setNavigationBarColor(Color.rgb(12,20,35));
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.rgb(12,20,35));
        webView = new WebView(this);
        webView.setBackgroundColor(Color.rgb(12,20,35));
        WebView.setWebContentsDebuggingEnabled(false);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true); // Required by EdgePilot dashboard.
        settings.setDomStorageEnabled(true); // Required for theme preference.
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        settings.setSaveFormData(false);
        settings.setGeolocationEnabled(false);
        // WebAuthn remains bound to the verified EdgePilot HTTPS origin and
        // Android Digital Asset Links. No JavaScript bridge, fake biometric
        // proof or credential interception is introduced.
        if (WebViewFeature.isFeatureSupported(WebViewFeature.WEB_AUTHENTICATION)) {
            WebSettingsCompat.setWebAuthenticationSupport(
                    settings, WebSettingsCompat.WEB_AUTHENTICATION_SUPPORT_FOR_APP);
        }
        CookieManager manager = CookieManager.getInstance();
        manager.setAcceptCookie(true); // Required for v0.19.11 HttpOnly session cookie.
        manager.setAcceptThirdPartyCookies(webView, false);
        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (allowed(request.getUrl())) return false;
                // Only an explicit, main-frame user click on these two
                // provider-owned help links can leave EdgePilot. The Public
                // site runs in the user's external browser, never our WebView.
                if (request.isForMainFrame() && request.hasGesture()
                        && approvedPublicHelp(request.getUrl())) {
                    try {
                        Intent browser = new Intent(Intent.ACTION_VIEW, request.getUrl());
                        browser.addCategory(Intent.CATEGORY_BROWSABLE);
                        startActivity(browser);
                    } catch (ActivityNotFoundException error) {
                        showNetworkError("No browser is available to open Public securely.");
                    }
                }
                // All other off-host navigation and all untrusted URL schemes
                // remain prohibited; no API secrets are appended to URLs.
                return true;
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                if (allowed(request.getUrl())) return null;
                return new WebResourceResponse("text/plain", "UTF-8", 403,
                        "Blocked", java.util.Collections.emptyMap(),
                        new ByteArrayInputStream(new byte[0]));
            }
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                pageFailed = false;
            }
            @Override public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                handler.cancel();
                pageFailed = true;
                showNetworkError("The HTTPS certificate is invalid. Connection blocked.");
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError err) {
                if (req.isForMainFrame()) {
                    pageFailed = true;
                    showNetworkError("Couldn't reach EdgePilot securely. Check your connection and retry.");
                }
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (!pageFailed && allowed(Uri.parse(url))) offlinePanel.setVisibility(View.GONE);
            }
        });
        root.addView(webView, new FrameLayout.LayoutParams(-1,-1));
        LinearLayout error = new LinearLayout(this);
        error.setOrientation(LinearLayout.VERTICAL);
        error.setGravity(Gravity.CENTER);
        error.setPadding(36,24,36,24);
        error.setBackgroundColor(Color.rgb(12,20,35));
        TextView errorText = new TextView(this);
        errorText.setText("EdgePilot is unavailable.");
        errorText.setTextSize(18);
        errorText.setTextColor(Color.WHITE);
        errorText.setGravity(Gravity.CENTER);
        errorText.setTag("message");
        error.addView(errorText, new LinearLayout.LayoutParams(-1,-2));
        Button retry = new Button(this);
        retry.setText("Retry securely");
        retry.setOnClickListener(v -> loadHome());
        error.addView(retry);
        offlinePanel = error;
        offlinePanel.setVisibility(View.GONE);
        root.addView(offlinePanel,new FrameLayout.LayoutParams(-1,-1));
        setContentView(root);
        loadHome();
    }

    private void showNetworkError(String message) {
        runOnUiThread(() -> {
            if (offlinePanel instanceof ViewGroup) {
                View messageView = ((ViewGroup) offlinePanel).getChildAt(0);
                if (messageView instanceof TextView) ((TextView) messageView).setText(message);
            }
            offlinePanel.setVisibility(View.VISIBLE);
        });
    }
    private void loadHome() {
        offlinePanel.setVisibility(View.GONE);
        webView.loadUrl(SITE);
    }
    @Override public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }
    @Override protected void onDestroy() {
        if (webView != null) { webView.destroy(); webView=null; }
        super.onDestroy();
    }
}
