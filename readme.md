# CPU羽毛球馆预约系统

本项目可用于CPU羽毛球场馆预约，使用前请务必先查询空余场地情况，再进行预约



## 运行要求

详见[requirements.yml](requirements.yml)

### 核心库

- Flask
- apscheduler
- faker
- json
- pytz
- requests

## 项目特点

本项目使用Flask搭建网页端,可部署在云服务器上,同时预约系统基于apscheduler库支持延迟提交,可选择立即提交某个申请,配合systemctl以及gunicorn等可以延迟提交

## 使用方法

### 获取本程序

```bash
git clone https://github.com/nanyeglm/cpu_badminton_online
cd cpu_badminton_online
```
### 安装环境
```bash
conda env create -f requirements.yml -n new_env_name
```
### 运行程序
运行app.py,开放端口18081,可自行修改
