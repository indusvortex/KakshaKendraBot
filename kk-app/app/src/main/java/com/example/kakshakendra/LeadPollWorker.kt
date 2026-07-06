package com.example.kakshakendra

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Background worker that polls the server every ~15 minutes for new leads
 * and shows a native Android notification when new leads arrive.
 */
class LeadPollWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        const val CHANNEL_ID = "kk_leads"
        const val CHANNEL_NAME = "New Leads"
        const val NOTIFICATION_ID_LEAD = 1001
        const val NOTIFICATION_ID_CHAT = 1002
        const val PREFS_NAME = "kk_poll_prefs"
        const val KEY_LAST_LEAD_COUNT = "last_lead_count"
        const val KEY_SESSION_COOKIE = "session_cookie"
        const val BASE_URL = "https://web-production-0e9ed.up.railway.app"
    }

    override suspend fun doWork(): Result {
        try {
            // Get the stored session cookie
            val prefs = applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            val sessionCookie = prefs.getString(KEY_SESSION_COOKIE, null)
            if (sessionCookie.isNullOrBlank()) {
                // User hasn't logged in through the app yet, skip
                return Result.success()
            }

            // Poll the notification endpoint
            val url = URL("$BASE_URL/api/app/notifications")
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "GET"
            conn.setRequestProperty("Cookie", sessionCookie)
            conn.connectTimeout = 10_000
            conn.readTimeout = 10_000

            val responseCode = conn.responseCode
            if (responseCode != 200) {
                // Auth failed or server error — don't show anything
                return Result.retry()
            }

            val body = conn.inputStream.bufferedReader().use { it.readText() }
            conn.disconnect()
            val json = JSONObject(body)

            val pendingLeads = json.optInt("pending_leads", 0)
            val unreadChats = json.optInt("unread_chats", 0)
            val lastKnownCount = prefs.getInt(KEY_LAST_LEAD_COUNT, 0)

            // Create notification channel (required for Android 8+)
            createNotificationChannel()

            // Show notification if there are NEW leads (count increased)
            if (pendingLeads > lastKnownCount && pendingLeads > 0) {
                val latestLead = json.optJSONObject("latest_lead")
                val name = latestLead?.optString("name", "Unknown") ?: "Unknown"
                val cls = latestLead?.optString("class", "TBD") ?: "TBD"
                val source = latestLead?.optString("source", "WhatsApp") ?: "WhatsApp"

                val newCount = pendingLeads - lastKnownCount
                val title = "🔔 ${newCount} New Lead${if (newCount > 1) "s" else ""}!"
                val body = "👤 $name · 🎓 $cls · via $source\n📞 $pendingLeads total pending calls"

                showNotification(
                    id = NOTIFICATION_ID_LEAD,
                    title = title,
                    body = body,
                    url = "/admin"
                )
            }

            // Show unread chat notification
            if (unreadChats > 0) {
                showNotification(
                    id = NOTIFICATION_ID_CHAT,
                    title = "💬 $unreadChats unread chat${if (unreadChats > 1) "s" else ""}",
                    body = "Students are waiting for your reply",
                    url = "/admin"
                )
            } else {
                // Clear chat notification if no unread
                NotificationManagerCompat.from(applicationContext).cancel(NOTIFICATION_ID_CHAT)
            }

            // Save current count for next comparison
            prefs.edit().putInt(KEY_LAST_LEAD_COUNT, pendingLeads).apply()

            return Result.success()
        } catch (e: Exception) {
            e.printStackTrace()
            return Result.retry()
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notifications for new student leads and messages"
                enableVibration(true)
                vibrationPattern = longArrayOf(0, 300, 200, 300)
            }
            val manager = applicationContext.getSystemService(NotificationManager::class.java)
            manager?.createNotificationChannel(channel)
        }
    }

    private fun showNotification(id: Int, title: String, body: String, url: String) {
        // Check permission on Android 13+
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(
                    applicationContext,
                    Manifest.permission.POST_NOTIFICATIONS
                ) != PackageManager.PERMISSION_GRANTED
            ) {
                return // No permission, skip
            }
        }

        val intent = Intent(applicationContext, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("open_url", url)
        }
        val pendingIntent = PendingIntent.getActivity(
            applicationContext,
            id,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(applicationContext, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setVibrate(longArrayOf(0, 300, 200, 300))
            .setContentIntent(pendingIntent)
            .build()

        NotificationManagerCompat.from(applicationContext).notify(id, notification)
    }
}
