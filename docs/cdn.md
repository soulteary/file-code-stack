# CDN 与缓存

先通过源站完成[公开对象验证](storage.md)与[上线验收](validation.md)，再接入 CDN。

## 接入 CDN 并检查缓存

图片域名和文件下载域名分别配置 CDN。源站指向 Traefik，回源 Host 与对应路由一致，使用 HTTPS 回源并验证源站证书。

业务域名已经解析到 CDN 时，源站填写服务器 IP 或独立源站域名，避免再次解析回 CDN 形成循环。使用 IP 回源时，还要确认 CDN 的回源 Host 和 TLS SNI 设置正确。

不会再覆盖、使用内容哈希命名的图片，可以在对象上设置：

```text
Cache-Control: public,max-age=31536000,immutable
```

同时设置正确的 `Content-Type`。可能被覆盖的 URL 使用较短 TTL，更新后按需要刷新缓存，不在 Traefik 上给所有响应统一追加 `immutable`。

只缓存公开内容的 GET、HEAD 响应，404 等错误响应使用较短缓存或不缓存。接入后重复检查 Range、ETag 和 `If-None-Match`，确认 CDN 没有改变下载行为。

带签名参数的 URL 不与忽略查询参数的公共缓存规则混用。JPEG、PNG、WebP、AVIF 等已经压缩的图片通常不需要额外 gzip。缓存命中率按实际服务域名观察，多个域名的汇总数据不能代表某一个图片服务。

公开桶允许匿名读取，因此接入 CDN 不代表源站只能由 CDN 访问。如果需要限制为 CDN 回源，再配置可靠的回源鉴权，或维护服务商公布的回源 IP 范围。Referer 不作为身份认证，也不信任未经核对的 forwarded headers。
