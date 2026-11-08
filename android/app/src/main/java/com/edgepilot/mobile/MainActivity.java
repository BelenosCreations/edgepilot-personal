package com.edgepilot.mobile;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.graphics.Color;
import android.content.Context;
import android.view.View;
import android.view.ViewGroup;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.Button;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;
import android.net.Uri;

/** Minimal Android shell for self-hosted EdgePilot. Backend never runs on the phone. */
public class MainActivity extends Activity {
    private WebView browser;
    private String site;
    @Override public void onCreate(Bundle saved){ super.onCreate(saved); openApp(); }
    private void openApp(){
        site=getPreferences(Context.MODE_PRIVATE).getString("site","");
        if (!site.startsWith("https://")){showSetup();return;}
        LinearLayout container=new LinearLayout(this);container.setOrientation(LinearLayout.VERTICAL);container.setBackgroundColor(Color.rgb(12,20,35));
        Button change=new Button(this);change.setText("EdgePilot · Change server"); change.setOnClickListener(v->showSetup());container.addView(change,new LinearLayout.LayoutParams(-1,-2));
        browser=new WebView(this);browser.getSettings().setJavaScriptEnabled(true);browser.getSettings().setDomStorageEnabled(false);
        browser.getSettings().setAllowFileAccess(false);browser.getSettings().setAllowContentAccess(false);
        browser.getSettings().setMixedContentMode(android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        browser.setWebViewClient(new WebViewClient(){@Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest req){
            Uri uri=req.getUrl();return !(uri.getScheme().equals("https") && uri.getHost()!=null && uri.getHost().equals(Uri.parse(site).getHost()));
        }});
        container.addView(browser,new LinearLayout.LayoutParams(-1,0,1));setContentView(container);browser.loadUrl(site);
    }
    private void showSetup(){
        EditText input=new EditText(this);input.setSingleLine(true);input.setHint("https://your-private-edgepilot-server");
        input.setText(getPreferences(Context.MODE_PRIVATE).getString("site",""));
        new AlertDialog.Builder(this).setTitle("EdgePilot server").setMessage("Enter the HTTPS address of your own EdgePilot backend. Use a secure private tunnel and never expose the backend publicly.").setView(input).setCancelable(false)
        .setPositiveButton("Connect",(d,w)->{String value=input.getText().toString().trim().replaceAll("/+$","");
            if(!value.startsWith("https://")){showSetup();return;}
            getPreferences(Context.MODE_PRIVATE).edit().putString("site",value).apply();openApp();})
        .setNegativeButton("Exit",(d,w)->finish()).show();
    }
    @Override public void onBackPressed(){if(browser!=null&&browser.canGoBack())browser.goBack();else super.onBackPressed();}
    @Override protected void onDestroy(){if(browser!=null){browser.destroy();browser=null;}super.onDestroy();}
}
