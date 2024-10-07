# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import requests
import json
from datetime import datetime, timedelta
from faker import Faker
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
import pytz
import os

# 导入 SQLAlchemy 相关模块
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # 请在生产环境中使用安全的随机字符串

# 初始化Faker
fake = Faker('zh_CN')

# 配置时区
tz = pytz.timezone('Asia/Shanghai')

# API URL和请求头
url = "https://cgyy.xiaorankeji.com/index.php?s=/api/order/addByUid"
headers = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": "https://cgyy.xiaorankeji.com/h5/index.html",
}

# 全局gym选项
gym_options = {}

# 中文符号到英文符号的映射
chinese_to_english_map = {
    '：': ':',
    '，': ',',
    '（': '(',
    '）': ')',
    '“': '"',
    '”': '"',
    '！': '!',
    '？': '?',
    '。': '.'
}

# 已生成的学工号记录文件
uids_file = 'uids.json'

# 配置数据库
engine = create_engine('sqlite:///tasks.sqlite', connect_args={'check_same_thread': False})
Base = declarative_base()
Session = scoped_session(sessionmaker(bind=engine))

# 定义任务模型
class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    job_id = Column(String, nullable=True)
    uid = Column(String)
    place_title_input = Column(String)
    start_time = Column(String)
    end_time = Column(String)
    order_date = Column(String)  # 预约日期
    order_name = Column(String)
    order_phone = Column(String)
    gym_selection = Column(String)
    submission_datetime = Column(DateTime)
    scheduled_execution_time = Column(DateTime, nullable=True)
    status = Column(String)
    execution_time = Column(DateTime, nullable=True)

# 创建表
Base.metadata.create_all(engine)

def convert_chinese_symbols(text):
    if text:
        for chinese, english in chinese_to_english_map.items():
            text = text.replace(chinese, english)
    return text

def normalize_place_title(title):
    title = title.replace('场地', '').strip()
    title = title.replace('号场', '').strip()
    if not title.endswith('号'):
        title += '号'
    return title

def fetch_gym_data(gym_ids):
    global gym_options
    for gym_id in gym_ids:
        gym_url = f"https://cgyy.xiaorankeji.com/index.php?s=/api/gym/detail&gymId={gym_id}"
        try:
            response = requests.get(gym_url)
            response.raise_for_status()
            data = response.json()
            if 'data' in data and 'detail' in data['data']:
                detail = data['data']['detail']
                gym_title = detail.get('title', '')
                category_id = detail.get('category_id', '')
                category_title = detail.get('category_title', '')
                store_id = detail.get('store_id', '')

                # 构建place_mapping
                place_mapping = {}
                for place in detail.get('placeList', []):
                    place_title = normalize_place_title(place.get('title', ''))
                    place_id = place.get('place_id', '')
                    place_mapping[place_title] = place_id

                # 构建interval_mapping
                interval_mapping = []
                for interval in detail.get('intervalList', []):
                    interval_mapping.append({
                        "Interval ID": interval.get('interval_id', ''),
                        "Week Day": interval.get('week_day', ''),
                        "Start Time": interval.get('start_time', ''),
                        "End Time": interval.get('end_time', ''),
                        "is_reserve": interval.get('is_reserve', 1)
                    })

                gym_options[gym_title] = {
                    "gym_id": gym_id,
                    "gym_title": gym_title,
                    "category_id": category_id,
                    "category_title": category_title,
                    "store_id": store_id,
                    "place_mapping": place_mapping,
                    "interval_mapping": interval_mapping
                }
            else:
                print(f"无法获取场馆 {gym_id} 的数据。")
        except Exception as e:
            print(f"获取场馆 {gym_id} 数据失败：{e}")

def generate_random_chinese_name():
    return fake.name()

def generate_random_phone():
    return fake.phone_number()

def load_generated_uids():
    if os.path.exists(uids_file):
        with open(uids_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        return {}

def save_generated_uids(uids):
    with open(uids_file, 'w', encoding='utf-8') as f:
        json.dump(uids, f, ensure_ascii=False, indent=4)

def generate_random_uid():
    import random
    prefixes = ['202019', '202018', '202020', '33210', '33200']
    uids = load_generated_uids()
    # 清理超过10天的UID
    current_time = datetime.now(tz)
    uids = {uid: timestamp for uid, timestamp in uids.items()
            if datetime.fromisoformat(timestamp) + timedelta(days=10) >= current_time}

    while True:
        prefix = random.choice(prefixes)
        if prefix.startswith('2020'):
            # 学号格式：2020****，共8位
            suffix = ''.join([str(random.randint(0,9)) for _ in range(4)])
        else:
            # 学号格式：33210*****，共10位
            suffix = ''.join([str(random.randint(0,9)) for _ in range(5)])
        uid = prefix + suffix
        if uid not in uids:
            uids[uid] = current_time.isoformat()
            save_generated_uids(uids)
            return uid

def calculate_end_time(start_time):
    start_time_obj = datetime.strptime(start_time, "%H:%M")
    end_time_obj = start_time_obj + timedelta(hours=1)
    return end_time_obj.strftime("%H:%M")

def get_week_day(order_date):
    date_obj = datetime.strptime(order_date, "%Y-%m-%d")
    week_day = (date_obj.weekday() + 1) % 7
    return week_day

def is_time_slot_available(week_day, start_time, end_time, interval_mapping):
    for interval in interval_mapping:
        if (int(interval["Week Day"]) == week_day and
            interval["Start Time"] == start_time and
            interval["End Time"] == end_time):
            if interval.get("is_reserve", 1) == 0:
                return True
            else:
                return False
    return False

def get_interval_id(week_day, start_time, end_time, interval_mapping):
    for interval in interval_mapping:
        if (int(interval["Week Day"]) == week_day and
            interval["Start Time"] == start_time and
            interval["End Time"] == end_time):
            return interval["Interval ID"]
    return None

def get_available_dates():
    current_date = datetime.now(tz)
    dates = [(current_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(0, 7)]
    return dates

# 配置 Job Store
jobstores = {
    'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')
}
scheduler = BackgroundScheduler(jobstores=jobstores, timezone=tz)
scheduler.start()

@app.before_first_request
def initialize():
    fetch_gym_data([10001, 10029])

@app.route('/', methods=['GET', 'POST'])
def index():
    session = Session()
    try:
        if request.method == 'POST':
            # 处理表单数据
            uid = convert_chinese_symbols(request.form.get('uid', ''))
            place_title_input = convert_chinese_symbols(request.form.get('place_title', ''))
            start_time = convert_chinese_symbols(request.form.get('start_time', ''))
            order_date = request.form.get('order_date', '')
            order_name = convert_chinese_symbols(request.form.get('order_name', ''))
            order_phone = convert_chinese_symbols(request.form.get('order_phone', ''))
            gym_selection = request.form.get('gym_selection', '')

            # 数据校验
            if not place_title_input or not start_time or not order_date or not gym_selection:
                flash("请填写所有必填项！", "error")
                return redirect(url_for('index'))

            # 获取提交方式
            submission_type = request.form.get('submission_type', '')
            if submission_type == 'immediate':
                # 立即提交
                submission_datetime = datetime.now(tz)
            elif submission_type == 'scheduled':
                # 获取提交时间
                submission_date = request.form.get('submission_date', '')
                submission_time = request.form.get('submission_time', '')
                if not submission_date or not submission_time:
                    flash("请填写提交时间的所有选项！", "error")
                    return redirect(url_for('index'))
                # 构建完整的提交时间字符串
                submission_time_str = f"{submission_date} {submission_time}"
                # 将提交时间字符串转换为datetime对象
                try:
                    submission_datetime = datetime.strptime(submission_time_str, "%Y-%m-%d %H:%M:%S")
                    submission_datetime = tz.localize(submission_datetime)
                except ValueError:
                    flash("提交时间格式错误！", "error")
                    return redirect(url_for('index'))

                # 检查提交时间是否在未来
                now = datetime.now(tz)
                if submission_datetime <= now:
                    flash("提交时间必须在当前时间之后！", "error")
                    return redirect(url_for('index'))
            else:
                flash("请选择提交方式！", "error")
                return redirect(url_for('index'))

            # 如果学工号留空，生成随机学工号
            if not uid:
                uid = generate_random_uid()

            # 如果姓名留空，生成随机姓名
            if not order_name:
                order_name = generate_random_chinese_name()

            # 如果联系电话留空，生成随机电话
            if not order_phone:
                order_phone = generate_random_phone()

            # 计算结束时间
            end_time = calculate_end_time(start_time)

            # 获取场馆数据
            gym_data = gym_options.get(gym_selection)
            if not gym_data:
                flash("无效的场馆选择！", "error")
                return redirect(url_for('index'))

            # 获取周几
            week_day = get_week_day(order_date)

            # 检查时间段是否可预约
            if not is_time_slot_available(week_day, start_time, end_time, gym_data["interval_mapping"]):
                flash("预约失败：选择的时间段不可预约！", "error")
                return redirect(url_for('index'))

            # 将预约数据存储到变量，以便在提交时使用
            appointment_data = {
                # 保存必要的预约信息
                'uid': uid,
                'place_title_input': place_title_input,
                'start_time': start_time,
                'end_time': end_time,
                'order_date': order_date,
                'order_name': order_name,
                'order_phone': order_phone,
                'gym_selection': gym_selection,
            }

            # 创建任务记录
            task = Task(
                uid=uid,
                place_title_input=place_title_input,
                start_time=start_time,
                end_time=end_time,
                order_date=order_date,  # 添加预约日期
                order_name=order_name,
                order_phone=order_phone,
                gym_selection=gym_selection,
                submission_datetime=datetime.now(tz),
                scheduled_execution_time=submission_datetime if submission_type == 'scheduled' else None,
            )

            if submission_type == 'immediate':
                # 立即提交
                submit_appointment(appointment_data, task.id)
                flash("预约已立即提交。", "success")
                appointment_info = appointment_data.copy()
                appointment_info['submission_datetime'] = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
                # 更新任务状态
                task.status = 'executed'
                task.execution_time = datetime.now(tz)
            else:
                # 调度任务，在指定时间执行
                job_id = f"appointment_{uid}_{int(datetime.now().timestamp())}"
                # 将任务ID添加到预约数据中
                appointment_data['task_id'] = task.id  # 注意，这里使用数据库生成的任务ID

                # 保存任务到数据库 before scheduling to ensure task.id is available
                session.add(task)
                session.commit()

                scheduler.add_job(
                    func=submit_appointment,
                    trigger='date',
                    run_date=submission_datetime,
                    args=[appointment_data, task.id],
                    id=job_id,
                    replace_existing=True
                )
                flash(f"您的预约请求已安排在 {submission_datetime.strftime('%Y-%m-%d %H:%M:%S')} 提交。", "success")
                appointment_info = appointment_data.copy()
                appointment_info['submission_datetime'] = submission_datetime.strftime('%Y-%m-%d %H:%M:%S')
                # 更新任务状态
                task.status = 'pending'
                task.scheduled_execution_time = submission_datetime
                task.job_id = job_id

            # 保存任务到数据库
            session.add(task)
            session.commit()

            return render_template('success.html', appointment_info=appointment_info)
        else:
            available_dates = get_available_dates()
            return render_template('index.html', gym_options=gym_options.keys(), available_dates=available_dates)
    finally:
        session.close()

def submit_appointment(appointment_data, task_id):
    session = Session()
    try:
        # 从appointment_data中提取数据
        uid = appointment_data['uid']
        place_title_input = appointment_data['place_title_input']
        start_time = appointment_data['start_time']
        end_time = appointment_data['end_time']
        order_date = appointment_data['order_date']
        order_name = appointment_data['order_name']
        order_phone = appointment_data['order_phone']
        gym_selection = appointment_data['gym_selection']

        # 获取场馆数据
        gym_data = gym_options.get(gym_selection)
        if not gym_data:
            print("预约失败：无效的场馆")
            return

        place_mapping = gym_data["place_mapping"]
        interval_mapping = gym_data["interval_mapping"]

        place_title = normalize_place_title(place_title_input)

        if place_title not in place_mapping:
            print(f"预约失败：无效的场地号 {place_title_input}")
            return

        week_day = get_week_day(order_date)

        if not is_time_slot_available(week_day, start_time, end_time, interval_mapping):
            print("预约失败：选择的时间段不可预约")
            return

        place_id = place_mapping.get(place_title)
        if place_id is None:
            print(f"预约失败：无效的场地名称 {place_title}")
            return

        interval_id = get_interval_id(week_day, start_time, end_time, interval_mapping)
        if interval_id is None:
            print("预约失败：无法找到匹配的时间段")
            return

        data = {
            "form": {
                "uid": uid,
                "place_id": place_id,
                "place_title": place_title,
                "interval_id": interval_id,
                "start_time": start_time,
                "end_time": end_time,
                "order_date": order_date,
                "order_phone": order_phone,
                "order_name": order_name,
                "order_student_id": "",
                "gym_id": gym_data["gym_id"],
                "gym_title": gym_data["gym_title"],
                "category_id": gym_data["category_id"],
                "category_title": gym_data["category_title"],
                "teacher_status": 0,
                "is_audit": 0,
                "store_id": gym_data["store_id"],
                "order_state": "用户预约成功",
                "is_admin": ""
            }
        }

        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            if response.status_code == 200:
                print(f"预约成功！学工号：{uid}")
                # 记录预约信息
                record_appointment(appointment_data)
            else:
                print(f"预约失败，状态码：{response.status_code}")
        except Exception as e:
            print(f"预约失败：{str(e)}")
        finally:
            # 更新任务状态
            if task_id:
                task = session.query(Task).get(task_id)
                if task:
                    task.status = 'executed'
                    task.execution_time = datetime.now(tz)
                    session.commit()
    finally:
        session.close()

def record_appointment(appointment_data):
    record_file = '/root/cypu_badminton_booking/record.txt'
    submission_time = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
    record_line = f"{appointment_data['uid']}, {appointment_data['place_title_input']}, {appointment_data['start_time']}, {appointment_data['end_time']}, {appointment_data['order_date']}, {appointment_data['order_name']}, {appointment_data['order_phone']}, {submission_time}\n"
    try:
        with open(record_file, 'a', encoding='utf-8') as f:
            f.write(record_line)
    except Exception as e:
        print(f"记录预约信息失败：{e}")

@app.route('/appointments', methods=['GET'])
def appointments():
    session = Session()
    try:
        selected_date = request.args.get('date', datetime.now(tz).strftime("%Y-%m-%d"))
        gym_selection = request.args.get('gym', list(gym_options.keys())[0])

        gym_data = gym_options.get(gym_selection)
        if not gym_data:
            flash("请选择有效的场馆！", "error")
            return redirect(url_for('index'))

        gym_id = gym_data["gym_id"]

        # 获取预约列表
        try:
            response = requests.get(
                f"https://cgyy.xiaorankeji.com/index.php?s=/api/order/listForGymOrder&state=用户预约成功,待管理员审核&orderDate={selected_date}&gymId={gym_id}"
            )
            response.raise_for_status()
            data = response.json()
            if 'data' in data and 'orderList' in data['data']:
                appointments_list = data['data']['orderList']
            else:
                appointments_list = []
        except Exception as e:
            flash(f"请求失败: {e}", "error")
            appointments_list = []

        # 处理预约数据
        for appointment in appointments_list:
            appointment['place_title'] = normalize_place_title(appointment.get('place_title', ''))

        # 对预约列表进行排序
        appointments_list.sort(key=lambda x: (
            int(x['place_title'].replace('号', '')),
            datetime.strptime(x['start_time'], "%H:%M")
        ))

        # 获取并排序场地列表
        place_list = sorted(gym_data['place_mapping'].keys(), key=lambda x: int(x.replace('号', '')))
        interval_mapping = gym_data['interval_mapping']

        # 构建时间段列表
        week_day = get_week_day(selected_date)
        intervals_for_day = [interval for interval in interval_mapping if int(interval['Week Day']) == week_day]

        # 获取所有可能的时间段
        time_slots_set = set()
        for interval in intervals_for_day:
            time_slot = f"{interval['Start Time']}-{interval['End Time']}"
            time_slots_set.add(time_slot)

        # 对时间段进行排序
        def time_slot_sort_key(time_slot):
            start_time_str = time_slot.split('-')[0]
            start_time_obj = datetime.strptime(start_time_str, "%H:%M")
            return start_time_obj

        time_slots = sorted(list(time_slots_set), key=time_slot_sort_key)

        # 构建预约状态表格
        status_table = []
        for time_slot in time_slots:
            row = {'time_slot': time_slot, 'places': []}
            for place_title in place_list:
                status = '可以预约'
                for appointment in appointments_list:
                    if (appointment['place_title'] == place_title and
                        f"{appointment['start_time']}-{appointment['end_time']}" == time_slot):
                        status = '已预约'
                        break
                else:
                    for interval in intervals_for_day:
                        if (interval['is_reserve'] == 1 and
                            interval['Start Time'] == time_slot.split('-')[0] and
                            interval['End Time'] == time_slot.split('-')[1]):
                            status = '已保留'
                            break
                row['places'].append({'place_title': place_title, 'status': status})
            status_table.append(row)

        available_dates = get_available_dates()
        return render_template(
            'appointments.html',
            appointments=appointments_list,
            gym_options=gym_options.keys(),
            selected_date=selected_date,
            selected_gym=gym_selection,
            available_dates=available_dates,
            status_table=status_table,
            place_list=place_list
        )
    finally:
        session.close()

@app.route('/tasks', methods=['GET'])
def view_tasks():
    session = Session()
    try:
        # 获取当前日期
        today_str = datetime.now(tz).strftime("%Y-%m-%d")

        # 获取过滤参数
        place_title = request.args.get('place_title', '')
        status = request.args.get('status', '')
        order_date = request.args.get('order_date', '')

        # 查询基础条件
        query = session.query(Task).filter(Task.order_date >= today_str)

        # 应用过滤条件
        if place_title:
            query = query.filter(Task.place_title_input == place_title)
        if status:
            query = query.filter(Task.status == status)
        if order_date:
            query = query.filter(Task.order_date == order_date)

        # 获取过滤后的任务
        tasks = query.order_by(Task.id.desc()).all()

        # 获取所有可能的筛选选项
        all_place_titles = session.query(Task.place_title_input).distinct().all()
        all_place_titles = [pt[0] for pt in all_place_titles if pt[0]]

        all_statuses = session.query(Task.status).distinct().all()
        all_statuses = [st[0] for st in all_statuses if st[0]]

        all_order_dates = session.query(Task.order_date).filter(Task.order_date >= today_str).distinct().all()
        all_order_dates = [od[0] for od in all_order_dates if od[0]]

        status_mapping = {
            'pending': '待执行',
            'executed': '已执行',
            'cancelled': '已取消'
        }

        return render_template('tasks.html',
                               tasks=tasks,
                               status_mapping=status_mapping,
                               all_place_titles=all_place_titles,
                               all_statuses=all_statuses,
                               all_order_dates=all_order_dates,
                               selected_place_title=place_title,
                               selected_status=status,
                               selected_order_date=order_date)
    finally:
        session.close()

@app.route('/tasks_data', methods=['GET'])
def tasks_data():
    session = Session()
    try:
        # 获取当前日期
        today_str = datetime.now(tz).strftime("%Y-%m-%d")

        # 获取过滤参数
        place_title = request.args.get('place_title', '')
        status = request.args.get('status', '')
        order_date = request.args.get('order_date', '')

        # 查询基础条件
        query = session.query(Task).filter(Task.order_date >= today_str)

        # 应用过滤条件
        if place_title:
            query = query.filter(Task.place_title_input == place_title)
        if status:
            query = query.filter(Task.status == status)
        if order_date:
            query = query.filter(Task.order_date == order_date)

        # 获取过滤后的任务
        tasks = query.order_by(Task.id.desc()).all()

        tasks_data = []
        for task in tasks:
            tasks_data.append({
                'id': task.id,
                'uid': task.uid,
                'place_title_input': task.place_title_input,
                'start_time': task.start_time,
                'end_time': task.end_time,
                'order_date': task.order_date,  # 返回预约日期
                'order_name': task.order_name,
                'order_phone': task.order_phone,
                'submission_datetime': task.submission_datetime.strftime('%Y-%m-%d %H:%M:%S'),
                'scheduled_execution_time': task.scheduled_execution_time.strftime('%Y-%m-%d %H:%M:%S') if task.scheduled_execution_time else '',
                'status': task.status,
                'execution_time': task.execution_time.strftime('%Y-%m-%d %H:%M:%S') if task.execution_time else '',
            })
        return jsonify(tasks_data)
    finally:
        session.close()

@app.route('/cancel_task/<int:task_id>', methods=['POST'])
def cancel_task(task_id):
    session = Session()
    try:
        task = session.query(Task).get(task_id)
        if task and task.status == 'pending':
            try:
                scheduler.remove_job(task.job_id)
                task.status = 'cancelled'
                session.commit()
                flash("任务已成功取消。", "success")
            except Exception as e:
                flash(f"取消任务失败：{e}", "error")
        else:
            flash("无法取消任务：任务不存在或已执行。", "error")
        return redirect(url_for('view_tasks'))
    finally:
        session.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=18081)
