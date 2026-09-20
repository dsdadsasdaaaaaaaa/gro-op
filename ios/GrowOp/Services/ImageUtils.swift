import UIKit

enum ImageUtils {
    /// Downscales so the long edge is at most `maxLongEdge` points and normalises orientation.
    static func downscaled(_ image: UIImage, maxLongEdge: CGFloat = 1600) -> UIImage {
        let size = image.size
        let longEdge = max(size.width, size.height)
        let scale = longEdge > maxLongEdge ? maxLongEdge / longEdge : 1.0
        let target = CGSize(width: (size.width * scale).rounded(.down), height: (size.height * scale).rounded(.down))
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        format.opaque = true
        let renderer = UIGraphicsImageRenderer(size: target, format: format)
        return renderer.image { _ in
            image.draw(in: CGRect(origin: .zero, size: target))
        }
    }

    /// JPEG bytes ready for upload (max 1600px long edge, quality 0.85).
    static func uploadData(for image: UIImage) -> Data? {
        downscaled(image).jpegData(compressionQuality: 0.85)
    }
}
