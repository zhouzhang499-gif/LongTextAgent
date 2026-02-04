# 云服务器部署指南

## 快速部署（推荐）

### 1. 购买云服务器

| 平台 | 推荐配置 | 价格参考 |
|------|----------|----------|
| 华为云 ECS | 2核4G | ¥50-100/月 |
| 阿里云 ECS | 2核4G | ¥50-100/月 |

### 2. 上传代码

```bash
# 在本地打包
git archive --format=tar.gz HEAD -o longtextagent.tar.gz

# 上传到服务器
scp longtextagent.tar.gz root@your-server:/opt/

# 在服务器解压
ssh root@your-server
cd /opt
tar -xzf longtextagent.tar.gz -C LongTextAgent
cd LongTextAgent
```

### 3. 一键部署

```bash
# 设置 API Key
export DEEPSEEK_API_KEY="sk-your-key"

# 运行部署脚本
chmod +x deploy.sh
./deploy.sh
```

## 手动部署

### 方式一：Docker Compose

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 创建 SSL 证书目录
mkdir ssl
# 将证书放入 ssl/cert.pem 和 ssl/key.pem

# 启动
export DEEPSEEK_API_KEY="sk-xxx"
docker-compose up -d
```

### 方式二：直接运行

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
export DEEPSEEK_API_KEY="sk-xxx"
python api_server.py
```

## SSL 证书获取

### Let's Encrypt 免费证书

```bash
# 安装 certbot
apt install certbot

# 获取证书（需要域名）
certbot certonly --standalone -d your-domain.com

# 证书位置
# /etc/letsencrypt/live/your-domain.com/fullchain.pem
# /etc/letsencrypt/live/your-domain.com/privkey.pem
```

### 自签名证书（测试用）

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout ssl/key.pem -out ssl/cert.pem \
    -subj "/CN=localhost"
```

## 验证部署

```bash
# 检查服务状态
docker-compose ps

# 测试 API
curl https://your-domain.com/health

# 查看日志
docker-compose logs -f
```

## 常见问题

### 端口被占用
```bash
# 查看占用端口的进程
lsof -i :8000
# 或
netstat -tlnp | grep 8000
```

### Docker 权限问题
```bash
sudo usermod -aG docker $USER
# 退出重新登录
```

### SSL 证书续期
```bash
# Let's Encrypt 证书 90 天过期
certbot renew
```
