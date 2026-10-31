# Keep the receiver/service entry points referenced only from the manifest.
-keep class com.example.localcallstyle.CallReceiver { *; }
-keep class com.example.localcallstyle.BootReceiver { *; }
-keep class com.example.localcallstyle.CallService { *; }
