# Keep kotlinx.serialization generated serializers.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers class kotlinx.serialization.json.** { *** Companion; }
-keepclasseswithmembers class kotlinx.serialization.json.** { kotlinx.serialization.KSerializer serializer(...); }
-keep,includedescriptorclasses class com.growop.app.**$$serializer { *; }
-keepclassmembers class com.growop.app.** { *** Companion; }
-keepclasseswithmembers class com.growop.app.** { kotlinx.serialization.KSerializer serializer(...); }
