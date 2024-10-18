#################################################
# YuanShen - 小猿口算 PK 答题 PoC
# Github: https://github.com/nkxingxh/YuanShenPK
# License: AGPL-3.0
#################################################

import copy
import time
import json
import asyncio
import subprocess
import re
import os

print(f"正在加载依赖库...")

from mitmproxy import http

import win32api
import win32con

operation_mode = "adb"  # win32api, adb
window_x, window_y, draw_size = 60, 400, 48

latest_data = []
latest_answers = []
latest_types = []
latest_pk = -1
can_start_answering = False

print(f"初始化完成!")

def time_sleep_micros(micros):
    if micros > 1000:
        time.sleep(micros/1_000_000)
        return
    end_time = time.perf_counter() + micros / 1_000_000
    while time.perf_counter() < end_time:
        pass  

def is_caps_lock_on():
    key_state = win32api.GetKeyState(0x14)
    return key_state != 0  

def win32_mouse_multi_drag(points, sleep_micros=50000):
    points = [(int(x), int(y)) for x, y in points]
    win32api.SetCursorPos(points[0])
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, points[0][0], points[0][1], 0, 0)
    time_sleep_micros(sleep_micros)
    for point in points[1:]:
        win32api.SetCursorPos(point)
        time_sleep_micros(sleep_micros)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, points[-1][0], points[-1][1], 0, 0)  

def adb_tap(x, y, sleep=0.6):
    tap_template = r'adb shell input tap %d %d'
    tap_command = tap_template % (x, y)
    process = subprocess.Popen(tap_command, shell=True)
    time.sleep(sleep)
    return

def adb_multi_drag(points, sleep=0.6):
    swipe_template = r'adb shell input swipe %d %d %d %d 1'
    commands = []
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1] 
        swipe_command = swipe_template % (x1, y1, x2, y2)
        commands.append(swipe_command)
    combined_command = " & ".join(commands)
    process = subprocess.Popen(combined_command, shell=True)
    time.sleep(sleep)

def draw_greater_than(origin_x, origin_y, size):
    print(f"[符号绘制] 大于")
    if operation_mode == "win32api":
        win32_mouse_multi_drag([(origin_x, origin_y), (origin_x + size, origin_y + size), (origin_x, origin_y + size)], 50000)
    elif operation_mode == "adb":
        adb_multi_drag([(origin_x, origin_y), (origin_x + size, origin_y + size), (origin_x, origin_y + size)])

def draw_less_than(origin_x, origin_y, size):
    print(f"[符号绘制] 小于")
    if operation_mode == "win32api":
        win32_mouse_multi_drag([(origin_x + size, origin_y), (origin_x, origin_y + size), (origin_x + size, origin_y + size)], 50000)
    elif operation_mode == "adb":
        adb_multi_drag([(origin_x + size, origin_y), (origin_x, origin_y + size), (origin_x + size, origin_y + size)])

async def answer_questions():
    global can_start_answering, latest_pk, latest_answers, latest_types, all_in_one, all_right
    global window_x, window_y, draw_size
    time_sleep_map = [
        12.12,
        1.35
    ]
    await asyncio.sleep(time_sleep_map[latest_pk])
    print(f"[自动答题] 开始...")

    for i, answer in enumerate(latest_answers):
        if is_caps_lock_on():
            print("[自动答题] 大写锁定启用, 答题中断。")
            break  
        question_type = latest_types[i]  
        if question_type in ["COMPARE", "EXPRESSION_COMPARE"]:
            print(f"[自动答题] 当前题型: 比较。")
            if answer == ">":
                draw_greater_than(window_x, window_y, draw_size)
            elif answer == "<":
                draw_less_than(window_x, window_y, draw_size)
            await asyncio.sleep(0.285)
            continue
        elif question_type == "ARITHMETIC":
            print(f"[自动答题] 当前题型: 算术。请自行实现!")
            continue
        else:
            print(f"[自动答题] 未知的题目类型! ", question_type)

    can_start_answering = False


def process_request(flow: http.HTTPFlow, IsResp: True):
    global only_one_question, all_in_one
    global latest_answers, latest_types, latest_pk, can_start_answering, latest_data
    try:
        if flow.request.path.startswith("/mitm/dataDecrypt"):
            print(f"[响应监听] 将使用收到的题目信息。")
            data = json.loads(flow.request.content)
        else:
            print(f"[响应监听] 将使用截获的题目信息。")
            data = json.loads(flow.response.content)  
        latest_data = copy.deepcopy(data)
        if 'examVO' in data and 'questions' in data['examVO']:
            print(f"[响应监听] 当前为 {data["examVO"]["questionCnt"]} 题 PK。对手为: {data['otherUser']['userName']}, 对方用时: {data['targetCostTime']/1000}s, 对方胜场: {data['otherWinCount']}")
            latest_pk = 0
            data['examVO']['questions'] = [data['examVO']['questions'][0]]
            questions = data['examVO']['questions']
        elif 'questions' in data:
            print(f"[响应监听] 当前为练习。")
            latest_pk = 1
            questions = data['questions']
        else:
            print(f"[响应监听] 跳过当前请求。")
            latest_pk = -1
            return
        flow.response.content = json.dumps(data).encode('utf-8')
        latest_answers = [question['answer'] for question in questions]
        latest_types = []
        for question in questions:
            if 'ruleType' in question:
                latest_types.append(question['ruleType'])
            else:
                answer = question['answer']
                if answer == ">" or answer == "<":
                    latest_types.append("COMPARE")
                elif answer.isdigit():
                    latest_types.append("ARITHMETIC")
                else:
                    latest_types.append("UNKNOWN")
        print("[响应监听] 答案为: ", latest_answers)
        can_start_answering = True
        asyncio.create_task(answer_questions())
    except json.JSONDecodeError:
        print(f"Failed to decode JSON from {flow.request.path}")

def inject_exercise(content):
    global priority_mode_js, only_one_question, all_in_one, all_right
    pattern = re.compile(r"\{(var\s+(\w+)\s*=\s*JSON\.parse\([^{}]*Base64\.decode\([^{}]*\.result\)[^{}]*\);)([^{}]*)\}")
    match = pattern.search(content)
    if match:
        entire_sentence = match.group(0)
        var_assignment = match.group(1)
        variable_name = match.group(2)
        remaining_content = match.group(3)
        locate_point = var_assignment + remaining_content
        print("[代码注入] exercise_ 关键点定位成功!")
    else:
        print("[代码注入] exercise_ 未匹配到目标代码, 需要沉淀!")
        return ""
    insert_code = var_assignment
    insert_code += f"""
fetch("https://xyks.yuanfudao.com/mitm/dataDecrypt", {{
    method: "POST",
    headers: {{
        "Content-Type": "application/json"
    }},
    body: JSON.stringify({variable_name})
}})
.then(response => {{
    if (!response.ok) {{
        throw new Error("服务器响应失败");
    }}
    return response.json();
}})
.then(data => {{
    {variable_name} = data;
    {remaining_content};
}})
.catch(error => {{
    console.error(error);
    {remaining_content};
}});"""
    if locate_point in content:
        new_content = content.replace(locate_point, insert_code)
    else:
        print("[代码注入] exercise_ 注入失败! 需要沉淀!")
        new_content = ""
    return new_content

def request(flow: http.HTTPFlow):
    if flow.request.path.startswith("/mitm/dataDecrypt"):
        flow.response = http.Response.make(
            200,
            flow.request.content,
            {"Content-Type": "application/json"}
        )
        process_request(flow, False)
        return

def response(flow: http.HTTPFlow):
    if flow.request.path.endswith(".js"):
        if flow.request.path.startswith("/bh5/leo-web-oral-pk/exercise_"):
            print("[响应监听] 将注入 exercise_ 脚本...")
            content = flow.response.content.decode('utf-8')
            new_content = inject_exercise(content)
            flow.response.content = new_content.encode('utf-8')
            return
    if flow.request.path.startswith("/leo-game-pk/android/math/pk/match?") \
    or flow.request.path.startswith("/leo-math/android/exams?"):
        process_request(flow, True)
        return
