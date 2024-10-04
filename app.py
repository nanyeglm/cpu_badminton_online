# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import requests
import json
from datetime import datetime, timedelta
from faker import Faker

app = Flask(__name__)
app.secret_key = 'nanye'  # 请在生产环境中使用安全的随机字符串

# 初始化Faker
fake = Faker('zh_CN')

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

def convert_chinese_symbols(text):
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
    current_date = datetime.now()
    dates = [(current_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(0, 7)]
    return dates

@app.before_first_request
def initialize():
    fetch_gym_data([10001, 10029])

@app.route('/', methods=['GET', 'POST'])
def index():
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
        if not uid or not place_title_input or not start_time or not order_date or not gym_selection:
            flash("请填写所有必填项！", "error")
            return redirect(url_for('index'))

        # 获取场馆数据
        gym_data = gym_options.get(gym_selection)
        if not gym_data:
            flash("请选择有效的场馆！", "error")
            return redirect(url_for('index'))

        place_mapping = gym_data["place_mapping"]
        interval_mapping = gym_data["interval_mapping"]

        place_title = normalize_place_title(place_title_input)

        if place_title not in place_mapping:
            flash(f"无效的场地号: {place_title_input}", "error")
            return redirect(url_for('index'))

        if not order_name:
            order_name = generate_random_chinese_name()

        if not order_phone:
            order_phone = generate_random_phone()

        end_time = calculate_end_time(start_time)
        week_day = get_week_day(order_date)

        if not is_time_slot_available(week_day, start_time, end_time, interval_mapping):
            flash("您选择的时间段不可预约，请选择其他时间。", "error")
            return redirect(url_for('index'))

        place_id = place_mapping.get(place_title)
        if place_id is None:
            flash(f"无效的场地名称: {place_title}", "error")
            return redirect(url_for('index'))

        interval_id = get_interval_id(week_day, start_time, end_time, interval_mapping)
        if interval_id is None:
            flash("无法找到匹配的时间段，请检查输入的时间和日期。", "error")
            return redirect(url_for('index'))

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
                flash("预约成功！", "success")
                return redirect(url_for('index'))
            else:
                flash(f"请求失败，状态码：{response.status_code}", "error")
                return redirect(url_for('index'))
        except Exception as e:
            flash(f"请求失败：{str(e)}", "error")
            return redirect(url_for('index'))
    else:
        available_dates = get_available_dates()
        return render_template('index.html', gym_options=gym_options.keys(), available_dates=available_dates)

@app.route('/appointments', methods=['GET'])
def appointments():
    selected_date = request.args.get('date', datetime.now().strftime("%Y-%m-%d"))
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
    
    # 对appointments_list进行排序
    appointments_list.sort(key=lambda x: (
        int(''.join(filter(str.isdigit, x['place_title']))),  # 提取场地号中的数字用于排序
        datetime.strptime(x['start_time'], "%H:%M")
    ))

    
    # 获取场地列表和时间段
    place_list = gym_data['place_mapping'].keys()
    interval_mapping = gym_data['interval_mapping']

    # 构建时间段列表
    week_day = get_week_day(selected_date)
    intervals_for_day = [interval for interval in interval_mapping if int(interval['Week Day']) == week_day]

    # 对时间段进行排序
    intervals_for_day.sort(key=lambda x: datetime.strptime(x['Start Time'], "%H:%M"))

    time_slots = []
    for interval in intervals_for_day:
        time_slot = f"{interval['Start Time']}-{interval['End Time']}"
        if time_slot not in time_slots:
            time_slots.append(time_slot)


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

if __name__ == '__main__':
    app.run(debug=True)
