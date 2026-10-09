export const adapt = text => text
  .replaceAll('pua_screen', 'android_screen')
  .replaceAll('iPhone Use', 'Android Use')
  .replaceAll('iPhone', 'Android')
  .replaceAll("version: '0.3.6'", "version: '0.2.3'")
  .replaceAll('截图已复制到剪贴板', '截图已刷新')
  .replaceAll('截图未能写入剪贴板', '截图刷新失败')
  .replaceAll('截图到剪贴板', '刷新截图')
  .replace('const FRAME_INTERVAL = 250;', 'const FRAME_INTERVAL = 33;')
  .replace('root.dataset.frameSeq = String(frame.seq);', `root.dataset.frameSeq = String(frame.seq);
    root.dataset.receivedFrames = String(Number(root.dataset.receivedFrames || 0) + 1);
    root.dataset.frameReceivedAt = String(performance.now());
    root.dataset.framePublishedAt = String((frame as typeof frame & { published_at?: number }).published_at || 0);`)
  .replace('image.onload = () => {', `image.onload = () => {
    root.dataset.presentedFrames = String(Number(root.dataset.presentedFrames || 0) + 1);
    root.dataset.imageDecodeMs = String(Math.round(performance.now() - Number(root.dataset.frameReceivedAt || performance.now())));
    root.dataset.publishedToImageLoadMs = String(Math.round(Date.now() - Number(root.dataset.framePublishedAt || Date.now())));`)
  .replace('consume(result.structuredContent);', `root.dataset.frameTransportMs = String(Math.round(performance.now() - started));
    consume(result.structuredContent);`);
