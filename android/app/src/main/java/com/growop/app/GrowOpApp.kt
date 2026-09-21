package com.growop.app

import android.app.Application
import coil3.ImageLoader
import coil3.PlatformContext
import coil3.SingletonImageLoader
import coil3.decode.DataSource
import coil3.decode.ImageSource
import coil3.fetch.FetchResult
import coil3.fetch.Fetcher
import coil3.fetch.SourceFetchResult
import coil3.key.Keyer
import coil3.memory.MemoryCache
import coil3.request.Options
import coil3.request.crossfade
import okio.Buffer

class GrowOpApp : Application(), SingletonImageLoader.Factory {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }

    /** Coil image loader whose photo fetcher goes through ApiClient, so thumbnails carry the API key (and the ingress session). */
    override fun newImageLoader(context: PlatformContext): ImageLoader =
        ImageLoader.Builder(context)
            .components {
                add(PhotoFetcher.Factory { container.appState.client })
                add(Keyer<PhotoImage> { data, _ -> "growop-photo-${data.id}-${if (data.thumb) "thumb" else "full"}" })
            }
            .memoryCache { MemoryCache.Builder().maxSizePercent(context, 0.2).build() }
            .crossfade(true)
            .build()
}

/** Coil model for a grow-brain photo (thumbnail or full image). */
data class PhotoImage(val id: Int, val thumb: Boolean)

class PhotoFetcher(
    private val data: PhotoImage,
    private val options: Options,
    private val client: () -> com.growop.app.data.ApiClient,
) : Fetcher {
    override suspend fun fetch(): FetchResult {
        val api = client()
        val bytes = if (data.thumb) api.photoThumbData(data.id) else api.photoImageData(data.id)
        return SourceFetchResult(
            source = ImageSource(Buffer().write(bytes), options.fileSystem),
            mimeType = "image/jpeg",
            dataSource = DataSource.NETWORK,
        )
    }

    class Factory(private val client: () -> com.growop.app.data.ApiClient) : Fetcher.Factory<PhotoImage> {
        override fun create(data: PhotoImage, options: Options, imageLoader: ImageLoader): Fetcher = PhotoFetcher(data, options, client)
    }
}
