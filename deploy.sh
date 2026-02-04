#!/bin/bash
# LongTextAgent 一键部署脚本
# 适用于 Ubuntu/Debian 服务器

set -e

echo "=========================================="
echo "LongTextAgent 部署脚本"
echo "=========================================="

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "正在安装 Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
fi

# 检查 Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "正在安装 Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# 创建 SSL 目录
mkdir -p ssl

# 检查 SSL 证书
if [ ! -f ssl/cert.pem ] || [ ! -f ssl/key.pem ]; then
    echo ""
    echo "⚠️ 未找到 SSL 证书！"
    echo ""
    echo "请选择："
    echo "1. 使用 Let's Encrypt 免费证书（需要域名）"
    echo "2. 使用自签名证书（仅测试用）"
    echo "3. 手动上传证书到 ssl/ 目录"
    read -p "请输入选择 (1/2/3): " ssl_choice
    
    case $ssl_choice in
        1)
            read -p "请输入你的域名: " domain
            sudo apt-get update
            sudo apt-get install -y certbot
            sudo certbot certonly --standalone -d $domain
            sudo cp /etc/letsencrypt/live/$domain/fullchain.pem ssl/cert.pem
            sudo cp /etc/letsencrypt/live/$domain/privkey.pem ssl/key.pem
            ;;
        2)
            echo "生成自签名证书..."
            openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
                -keyout ssl/key.pem -out ssl/cert.pem \
                -subj "/CN=localhost"
            ;;
        3)
            echo "请将证书文件放入 ssl/ 目录："
            echo "  - ssl/cert.pem (证书)"
            echo "  - ssl/key.pem (私钥)"
            exit 0
            ;;
    esac
fi

# 检查环境变量
if [ -z "$DEEPSEEK_API_KEY" ]; then
    read -p "请输入 DEEPSEEK_API_KEY: " api_key
    export DEEPSEEK_API_KEY=$api_key
    echo "DEEPSEEK_API_KEY=$api_key" >> .env
fi

# 构建并启动
echo ""
echo "正在构建并启动服务..."
docker-compose up -d --build

echo ""
echo "=========================================="
echo "✅ 部署完成！"
echo "=========================================="
echo ""
echo "服务地址："
echo "  - HTTP:  http://your-server-ip (会重定向到 HTTPS)"
echo "  - HTTPS: https://your-server-ip"
echo "  - API文档: https://your-server-ip/docs"
echo ""
echo "管理命令："
echo "  - 查看日志: docker-compose logs -f"
echo "  - 停止服务: docker-compose down"
echo "  - 重启服务: docker-compose restart"
echo ""
