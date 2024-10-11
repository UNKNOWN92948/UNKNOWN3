import os
import json
import httpx
import random
import asyncio
import argparse
from urllib.parse import parse_qs
from colorama import init, Fore, Style
from fake_useragent import UserAgent
from base64 import b64decode
from datetime import datetime

init(autoreset=True)
token_file = ".match_tokens.json"
log_file = "http.log"
data_file = "data.txt"
config_file = ".config.json"

red = Fore.LIGHTRED_EX
green = Fore.LIGHTGREEN_EX
yellow = Fore.LIGHTYELLOW_EX
magenta = Fore.LIGHTMAGENTA_EX
white = Fore.LIGHTWHITE_EX
line = white + "~" * 50

class Config:
    def __init__(self, auto_claim: bool, auto_solve_task: bool, auto_play_game: bool, low_point: int, high_point: int):
        self.auto_claim = auto_claim
        self.auto_solve_task = auto_solve_task
        self.auto_play_game = auto_play_game
        self.low_point = low_point
        self.high_point = high_point

class MatchTod:
    def __init__(self, id: int, query: str, config: Config, update_ua: bool):
        self.simple_log(f"Start account number: {id + 1}")
        parser = lambda data: {key: value[0] for key, value in parse_qs(data).items()}
        user = parser(query).get("user")
        self.valid = bool(user)
        self.config = config

        if not self.valid:
            self.simple_log(f"{red}Invalid user data.")
            return

        self.user = json.loads(user)
        self.query = query
        self.ses = httpx.AsyncClient(verify=False)
        self.headers = {
            "Host": "tgapp-api.matchain.io",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Linux; Android 11; K) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/106.0.5249.79 Mobile Safari/537.36",
            "Content-Type": "application/json",
            "Origin": "https://tgapp.matchain.io",
            "X-Requested-With": "org.telegram.messenger",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://tgapp.matchain.io/",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en,id-ID;q=0.9,id;q=0.8,en-US;q=0.7",
        }
        self.ua_file = f"user_agents/{self.user.get('username')}.json"
        if update_ua:
            self.update_user_agent()

    async def http(self, url, headers, data=None):
        while True:
            try:
                if not await file_exists(log_file):
                    await write_file(log_file, "")
                logsize = await get_file_size(log_file)
                if logsize / 1024 / 1024 > 1:
                    await write_file(log_file, "")
                if data is None:
                    res = await self.ses.get(url, headers=headers, timeout=30)
                else:
                    res = await self.ses.post(url, headers=headers, timeout=30, data=data)
                
                try:
                    text = res.text
                except UnicodeDecodeError:
                    text = res.content.decode('utf-8', errors='replace')
                await append_file(log_file, f"{text}\n")
                return res
            except httpx.NetworkError:
                self.simple_log(f"{red}Network error!")
                await asyncio.sleep(random.randint(1, 2))
            except httpx.TimeoutException:
                self.simple_log(f"{red}Connection timeout!")
                await asyncio.sleep(random.randint(1, 2))
            except httpx.RemoteProtocolError:
                self.simple_log(f"{red}Server disconnected without sending response")
                await asyncio.sleep(random.randint(1, 2))

    def simple_log(self, msg):
        print(f"{msg}")

    def is_expired(self, token):
        try:
            if token is None or isinstance(token, bool):
                return True
            header, payload, sign = token.split(".")
            deload = b64decode(payload + "==")
            jeload = json.loads(deload)
            now = int(datetime.now().timestamp()) + 200
            return now > jeload.get("exp")
        except Exception as e:
            self.simple_log(f"Error decoding token: {e}")
            return True

    async def login(self):
        login_url = "https://tgapp-api.matchain.io/api/tgapp/v1/user/login"
        login_data = {
            "uid": self.user.get("id"),
            "first_name": self.user.get("first_name"),
            "last_name": self.user.get("last_name"),
            "username": self.user.get("username"),
            "tg_login_params": self.query,
        }
        res = await self.http(login_url, self.headers, json.dumps(login_data))
        if not self.check_code(res.json()):
            return False
        return res.json().get("data", {}).get("token")

    def check_code(self, data: dict):
        code = data.get("code")
        msg = data.get("msg", "")
        err = data.get("err", "")
        if "You've already made a purchase." in msg:
            return "buy"
        if "user not found" == err:
            self.simple_log(f"{yellow}This telegram account has not been registered with the bot.")
            return False
        if code != 200:
            self.simple_log(f"{red}Code: {code}, {(msg if msg else err)}")
            return False
        return True

    def update_user_agent(self):
        ua = UserAgent(platforms="mobile").random
        uas = {str(self.user.get('id')): ua}
        self.headers["User-Agent"] = ua
        if not os.path.exists('user_agents'):
            os.makedirs('user_agents')
        with open(self.ua_file, "w") as file:
            json.dump(uas, file, indent=4)
        self.simple_log(f"{green}User agent updated for {self.user.get('username')}")

    async def start(self):
        uid = str(self.user.get("id"))
        first_name = self.user.get("first_name")
        self.simple_log(f"{magenta}Browser: Mozilla/Linux")
        self.simple_log(f"{green}Login {white}{first_name}")

        tokens = json.loads(await read_file(token_file))
        if not os.path.exists(self.ua_file):
            uas = {uid: UserAgent(platforms="mobile").random}
            await write_file(self.ua_file, json.dumps(uas, indent=4))
        else:
            uas = json.loads(await read_file(self.ua_file))
        
        ua = uas.get(uid)
        self.headers["User-Agent"] = ua
        token = tokens.get(uid)
        if self.is_expired(token):
            token = await self.login()
            if not token:
                return
            tokens[uid] = token
            await write_file(token_file, json.dumps(tokens, indent=4))
        self.headers["Authorization"] = token
        self.simple_log(f"{green}Success login!")
        profile_url = "https://tgapp-api.matchain.io/api/tgapp/v1/user/profile"
        reward_url = "https://tgapp-api.matchain.io/api/tgapp/v1/point/reward"
        reward_claim_url = "https://tgapp-api.matchain.io/api/tgapp/v1/point/reward/claim"
        farming_url = "https://tgapp-api.matchain.io/api/tgapp/v1/point/reward/farming"
        balance_url = "https://tgapp-api.matchain.io/api/tgapp/v1/point/balance"
        tasks_url = "https://tgapp-api.matchain.io/api/tgapp/v1/point/task/list"
        task_complete_url = "https://tgapp-api.matchain.io/api/tgapp/v1/point/task/complete"
        task_claim_url = "https://tgapp-api.matchain.io/api/tgapp/v1/point/task/claim"
        daily_task_url = "https://tgapp-api.matchain.io/api/tgapp/v1/daily/task/status"
        buy_booster_url = "https://tgapp-api.matchain.io/api/tgapp/v1/daily/task/purchase"
        basic_data = {"uid": int(uid)}
        res = await self.http(profile_url, self.headers, json.dumps(basic_data))
        code = res.json().get("code")
        if code != 200:
            err = res.json().get("err")
            self.simple_log(f"{red}Code: {code}, {err}")
            return False
        data = res.json().get("data")
        is_bot = data.get("IsBot")
        balance = data.get("Balance") / 1000
        self.simple_log(f"{green}Balance: {white}{balance:.3f}")
        self.simple_log(f"{green}Bot flag: {white}{is_bot}")
        res = await self.http(daily_task_url, self.headers)
        if not self.check_code(res.json()):
            return False
        data = res.json().get("data")
        for da in data:
            current_count = da.get("current_count")
            task_count = da.get("task_count")
            point = da.get("point")
            dtype = da.get("type")
            if dtype == "quiz":
                continue
            if balance < point:
                continue
            if current_count == task_count:
                continue
            buy_data = {"uid": int(uid), "type": dtype}
            res = await self.http(buy_booster_url, self.headers, json.dumps(buy_data))
            cdr = self.check_code(res.json())
            if cdr == "buy":
                self.simple_log(f"{yellow}Has purchased a {dtype} booster")
            elif not cdr:
                return False
            else:
                self.simple_log(f"{green}Successful purchase of a {dtype} booster")

        next_claim_timestamp = 3600
        if self.config.auto_claim:
            while True:
                res = await self.http(reward_url, self.headers, json.dumps(basic_data))
                code = res.json().get("code")
                if not self.check_code(res.json()):
                    return False

                data = res.json().get("data", {})
                reward = data.get("reward")
                next_claim_timestamp = (data.get("next_claim_timestamp", (int(datetime.now().timestamp() + 1000) * 1000)) / 1000)
                now = int(datetime.now().timestamp())
                if reward == 0 or reward is None:
                    res = await self.http(farming_url, self.headers, json.dumps(basic_data))
                    if not self.check_code(res.json()):
                        return False
                    self.simple_log(f"{green}Success start farming!")
                    await asyncio.sleep(random.randint(2, 3))
                    continue
                if now > next_claim_timestamp:
                    res = await self.http(reward_claim_url, self.headers, json.dumps(basic_data))
                    if not self.check_code(res.json()):
                        return False
                    self.simple_log(f"{green}Success claim farming!")
                    await asyncio.sleep(random.randint(2, 3))
                    continue
                self.simple_log(f"{yellow}Not the time to claim farming")
                break
        if self.config.auto_solve_task:
            res = await self.http(tasks_url, self.headers, json.dumps(basic_data))
            if not self.check_code(res.json()):
                return False
            data = res.json().get("data", {})
            task_keys = list(data.keys())
            for key in task_keys:
                tasks = data.get(key)
                for task in tasks:
                    name = task.get("name")
                    complete = task.get("complete")
                    if complete:
                        self.simple_log(f"{red}Task {name}: Already completed!")
                        continue
                    complete_data = {"uid": int(uid), "type": name}
                    res = await self.http(task_complete_url, self.headers, json.dumps(complete_data))
                    if not self.check_code(res.json()):
                        continue
                    await asyncio.sleep(random.randint(2, 3))
                    res = await self.http(task_claim_url, self.headers, json.dumps(complete_data))
                    code = res.json().get("code")
                    if code != 200:
                        continue
                    self.simple_log(f"{green}Task {name}: Success complete task")
            res = await self.http(balance_url, self.headers, json.dumps(basic_data))
            if not self.check_code(res.json()):
                return False
            balance = res.json().get("data") / 1000
        if self.config.auto_play_game:
            game_url = "https://tgapp-api.matchain.io/api/tgapp/v1/game/play"
            game_claim_url = "https://tgapp-api.matchain.io/api/tgapp/v1/game/claim"
            while True:
                res = await self.http(game_url, self.headers)
                if not self.check_code(res.json()):
                    return False
                data = res.json().get("data", {})
                game_id = data.get("game_id")
                game_count = data.get("game_count")
                self.simple_log(f"{green}Available game tickets: {white}{game_count}")
                if int(game_count) <= 0:
                    self.simple_log(f"{red}No more game tickets. Stopping.")
                    break
                await countdown(35)
                point = random.randint(self.config.low_point, self.config.high_point)
                game_claim_data = {"game_id": game_id, "point": point}
                res = await self.http(game_claim_url, self.headers, json.dumps(game_claim_data))
                if not self.check_code(res.json()):
                    return False
                self.simple_log(f"{green}Successfully played a game with {white}{point} {green}points")
                await asyncio.sleep(random.randint(2, 3))

        self.simple_log(f"{green}Final Balance: {white}{balance:.3f}")
        return balance

async def countdown(t):
    for i in range(t, 0, -1):
        minute, second = divmod(i, 60)
        hour, minute = divmod(minute, 60)
        second = str(second).zfill(2)
        minute = str(minute).zfill(2)
        hour = str(hour).zfill(2)
        print(f"waiting {hour}:{minute}:{second} ", flush=True, end="\r")
        await asyncio.sleep(1)
    print("                       ", flush=True, end="\r")

async def file_exists(filepath):
    return await asyncio.get_event_loop().run_in_executor(None, os.path.exists, filepath)

async def get_file_size(filepath):
    return await asyncio.get_event_loop().run_in_executor(None, os.path.getsize, filepath)

async def read_file(filepath):
    with open(filepath, "r") as file:
        return file.read()

async def write_file(filepath, data):
    with open(filepath, "w") as file:
        file.write(data)

async def append_file(filepath, data):
    with open(filepath, "a") as file:
        file.write(data)

def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')

def check_user_agents_exist():
    return os.path.exists('user_agents') and any(os.scandir('user_agents'))

async def main():
    clear_terminal()
    print(Fore.GREEN + Style.BRIGHT + r"""
  _                
 | | | |             | |               
 | |_| |  __ _   ___ | | __  ___  _ __ 
 |  _  | / _` | / __|| |/ / / _ \| '__|
 | | | || (_| || (__ |   < |  __/| |   
 \_| |_/ \__,_| \___||_|\_\ \___||_| 
    """ + Style.RESET_ALL)

    if not await file_exists(data_file):
        await write_file(data_file, "")
    if not await file_exists(token_file):
        await write_file(token_file, json.dumps({}))
    if not await file_exists(config_file):
        await write_file(
            config_file,
            json.dumps({
                "auto_claim": True,
                "auto_play_game": True,
                "auto_solve_task": True,
                "game_point": {"low": 100, "high": 150},
            })
        )

    if not await file_exists('user_agents'):
        os.makedirs('user_agents')

    update_ua = False
    if check_user_agents_exist():
        update_ua = input("Do you want to update user agents? (y/n): ").strip().lower() == 'y'

    arg = argparse.ArgumentParser()
    arg.add_argument("--data", "-D", default=data_file)
    arg.add_argument("--action", "-A")
    args = arg.parse_args()

    total_balance = 0
    while True:
        clear_terminal()
        print(Fore.GREEN + Style.BRIGHT + r"""
  _                
 | | | |             | |               
 | |_| |  __ _   ___ | | __  ___  _ __ 
 |  _  | / _` | / __|| |/ / / _ \| '__|
 | | | || (_| || (__ |   < |  __/| |   
 \_| |_/ \__,_| \___||_|\_\ \___||_| 
    """ + Style.RESET_ALL)
        
print(Fore.CYAN + "MatchQuest Script Edited by @Dhiraj_9619 💫" + Style.RESET_ALL)
print(Fore.CYAN + "Script created by @pemulungonlinechannel" + Style.RESET_ALL)
        
        print(line)
       if not await file_exists(args.data):
           print(f"{white}Data file: {args.data} {red} file not found!")
           return
        datas = [i for i in (await read_file(args.data)).splitlines() if len(i) > 0]
        config = json.loads(await read_file(config_file))
        cfg = Config(
            auto_claim=config.get("auto_claim", True),
            auto_solve_task=config.get("auto_solve_task", True),
            auto_play_game=config.get("auto_play_game", True),
            low_point=config.get("game_point", {}).get("low", 100),
            high_point=config.get("game_point", {}).get("high", 100),
        )

        menu = f"""
{white}Data file: {green} {data_file}
{line}
{green}Total data: {white}{len(datas)}
{line}
Menu:
1.) Set on/off auto claim ({(green + 'active' if cfg.auto_claim else red + 'non-active')}{white})
2.) Set on/off auto play game ({(green + 'active' if cfg.auto_play_game else red + 'non-active')}{white})
3.) Set on/off auto solve task ({(green + 'active' if cfg.auto_solve_task else red + 'non-active')}{white})
4.) Set game point ({green}{cfg.low_point}-{cfg.high_point}{white})
5.) Start bot

{white}Note: Ctrl + C to exit!
    """
        print(menu)
        opt = args.action
        if opt is None:
            opt = input("Input number: ")
        print(line)
        try:
            if int(opt) not in [1, 2, 3, 4, 5]:
                print(f"{red}Enter the correct number of menu!")
                input(f"{yellow}Press enter to continue")
                continue
        except ValueError:
            print(f"{red}Enter the correct number of menu!")
            input(f"{yellow}Press enter to continue")
        if opt == "1":
            config["auto_claim"] = not cfg.auto_claim
            await write_file(config_file, json.dumps(config, indent=4))
            print(f"{green}Successfully made auto_claim config changes")
            input(f"{yellow}Press enter to continue")
            continue
        if opt == "2":
            config["auto_play_game"] = not cfg.auto_play_game
            await write_file(config_file, json.dumps(config, indent=4))
            print(f"{green}Successfully made auto_play_game config changes")
            input(f"{yellow}Press enter to continue")
            continue
        if opt == "3":
            config["auto_solve_task"] = not cfg.auto_solve_task
            await write_file(config_file, json.dumps(config, indent=4))
            print(f"{green}Successfully made auto_solve_task config changes")
            input(f"{yellow}Press enter to continue")
            continue

        if opt == "4":
            low_point = input("Input lowest point: ")
            high_point = input("Input highest point: ")
            try:
                if int(low_point) > int(high_point):
                    print(f"{red}The lowest point cannot exceed the highest point.")
                    input(f"{yellow}Press enter to continue")
                    continue
            except ValueError:
                print(f"{red}Enter the correct number.")
                input(f"{yellow}Press enter to continue")
                continue

            config["game_point"]["low"] = int(low_point)
            config["game_point"]["high"] = int(high_point)
            await write_file(config_file, json.dumps(config, indent=4))
            print(f"{green}Successfully made game_point config changes")
            input(f"{yellow}Press enter to continue")
            continue
        if opt == "5":
            visited_accounts = set()
            while True:
                for no, data in enumerate(datas):
                    if no in visited_accounts:
                        continue
                    matchq = MatchTod(id=no, query=data, config=cfg, update_ua=update_ua)
                    if not matchq.valid:
                        print(f"{yellow}It looks like account {no + 1} data has the wrong format.")
                        print(line)
                        continue
                    balance = await matchq.start()
                    total_balance += balance
                    visited_accounts.add(no)
                    print(line)
                print(f"{green}Total balance of all accounts: {white}{total_balance:.3f}")
                open_menu = input("No new accounts to process. Return to main menu? (y/n): ").strip().lower()
                if open_menu == 'y':
                    break
                else:
                    exit()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        exit()
