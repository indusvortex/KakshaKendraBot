package com.example.kakshakendra

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.net.http.SslError
import android.os.Build
import android.os.Bundle
import android.webkit.CookieManager
import android.webkit.SslErrorHandler
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

class MainActivity : ComponentActivity() {
    private lateinit var webView: WebView

    companion object {
        const val BASE_URL = "https://web-production-0e9ed.up.railway.app"
        const val WORK_NAME = "kk_lead_poll"
    }

    // Permission launcher for Android 13+ notification permission
    private val notificationPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) {
                startLeadPolling()
            }
        }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Enable web debugging for chrome://inspect
        WebView.setWebContentsDebuggingEnabled(true)

        webView = WebView(this).apply {
            webViewClient = object : WebViewClient() {
                @Deprecated("Deprecated in Java")
                override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
                    view?.loadUrl(url ?: "")
                    return true
                }

                override fun onReceivedSslError(view: WebView?, handler: SslErrorHandler?, error: SslError?) {
                    handler?.proceed() // Proceed on SSL certificate errors
                }

                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    // Capture session cookie after page loads (especially after login)
                    saveCookieForWorker(url)
                }
            }

            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.databaseEnabled = true
            settings.loadWithOverviewMode = true
            settings.useWideViewPort = true
            settings.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW

            // Allow cookies
            val cookieManager = CookieManager.getInstance()
            cookieManager.setAcceptCookie(true)
            cookieManager.setAcceptThirdPartyCookies(this, true)

            // Disable zoom
            settings.displayZoomControls = false
            settings.builtInZoomControls = false

            // Set UserAgent
            settings.userAgentString = settings.userAgentString + " KakshaKendraApp"
        }

        setContentView(webView)

        // Check for URL from notification tap
        val openUrl = intent.getStringExtra("open_url")
        if (openUrl != null) {
            webView.loadUrl("$BASE_URL$openUrl")
        } else {
            webView.loadUrl("$BASE_URL/login")
        }

        // Request notification permission and start polling
        requestNotificationPermissionAndStartPolling()
    }

    /**
     * Saves the session cookie from the WebView so the background
     * LeadPollWorker can authenticate API requests.
     */
    private fun saveCookieForWorker(url: String?) {
        if (url == null) return
        try {
            val cookieManager = CookieManager.getInstance()
            val cookies = cookieManager.getCookie(url)
            if (!cookies.isNullOrBlank() && cookies.contains("session")) {
                val prefs = getSharedPreferences(LeadPollWorker.PREFS_NAME, MODE_PRIVATE)
                prefs.edit().putString(LeadPollWorker.KEY_SESSION_COOKIE, cookies).apply()
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    /**
     * Ask for notification permission (Android 13+) then schedule periodic polling.
     */
    private fun requestNotificationPermissionAndStartPolling() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            when {
                ContextCompat.checkSelfPermission(
                    this, Manifest.permission.POST_NOTIFICATIONS
                ) == PackageManager.PERMISSION_GRANTED -> {
                    startLeadPolling()
                }
                else -> {
                    notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                }
            }
        } else {
            // Pre-Android 13: no runtime permission needed
            startLeadPolling()
        }
    }

    /**
     * Schedule a periodic background worker that checks for new leads
     * every 15 minutes (minimum interval for WorkManager).
     */
    private fun startLeadPolling() {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

        val pollRequest = PeriodicWorkRequestBuilder<LeadPollWorker>(
            15, TimeUnit.MINUTES
        )
            .setConstraints(constraints)
            .build()

        WorkManager.getInstance(this).enqueueUniquePeriodicWork(
            WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            pollRequest
        )
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (::webView.isInitialized && webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }
}
