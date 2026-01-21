import websocket
import json
import threading
import time

# --- 1. 核心配置（包含最新的 Cookie） ---
WS_URL = "wss://stake.com/_api/websockets"

# 需要过滤显示的用户名列表（只打印这些用户的高额投注）
FILTERED_USERS = [
    "ptkuqeepr",
    "sctb4471"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Origin": "https://stake.com",
    "Accept-Language": "zh-HK,zh;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Cookie": 'currency_hideZeroBalances=false; fiat_number_format=en; locale=zh; intercom-device-id-cx1ywgf2=2356c25f-dcbe-4960-8b16-87954ef6497a; cookie_consent=true; _ga=GA1.1.1975436884.1742816225; _hjSessionUser_5261158=eyJpZCI6ImY1NmMxMTZiLWZlNzctNWFiZS1iMDRjLWZhMGQwODQ3MWIyNyIsImNyZWF0ZWQiOjE3NDI4MTYyMjcwOTAsImV4aXN0aW5nIjp0cnVlfQ==; oddsFormat=decimal; sportMarketGroupMap={}; quick_bet_popup=false; session_info={"id":"c31615b2-57d8-476a-8afc-4d921c3860f6","sessionName":"Chrome (Unknown)","ip":"119.236.23.107","country":"HK","city":"Central","active":true,"updatedAt":"Fri, 23 May 2025 15:16:09 GMT","__typename":"UserSession"}; fullscreen_preference=false; cookie_last_vip_tab=rewards; level_up_vip_flag=; leftSidebarView_v2=minimized; currency_currencyView=usd; currency_currency=usdt; sidebarView=chat; _cfuvid=wGdI_05JZpEhflfkUi6W0N1VGixURsKvgX68_3koWNk-1766932430486-0.0.1.1-604800000; mp_e29e8d653fb046aa5a7d7b151ecf6f99_mixpanel=%7B%22distinct_id%22%3A%22dbc212fe-c0e7-4876-857a-faa65b2b4097%22%2C%22%24device_id%22%3A%22a1f7057b-d2bf-473e-a06b-95ccbba8c2ea%22%2C%22%24initial_referrer%22%3A%22https%3A%2F%2Fstake.com%2F%3Fpromo%3Dnewbday3b25%26__cf_chl_tk%3D83W74DBNDRMPpXgEVWX2USN21Km.FFa6oE6Dg3dROHY-1748013328-1.0.1.1-AAEjU6xQPx4loFfQGkuUiZmPYroMbpKJpCQWVmGQnGs%22%2C%22%24initial_referring_domain%22%3A%22stake.com%22%2C%22__mps%22%3A%7B%7D%2C%22__mpso%22%3A%7B%7D%2C%22__mpus%22%3A%7B%7D%2C%22__mpa%22%3A%7B%7D%2C%22__mpu%22%3A%7B%7D%2C%22__mpr%22%3A%5B%5D%2C%22__mpap%22%3A%5B%5D%2C%22%24user_id%22%3A%22dbc212fe-c0e7-4876-857a-faa65b2b4097%22%7D; intercom-session-cx1ywgf2=MlRUTW9IWGV4TEJ2Nnd0S092NUlWWXBhL1RlblJrVzRvQjJSWEgvZUZFaFJpb3Q2T1Blc3h0ZDNEZXd5cmx2bTJCODBRNTcxRTBvUHlDdW9VeHV5eHRGdmJJQUNlUndUVE4zbGg1NHJyTDg9LS1wQitUbDlFUit1SlhyNTlpdTY4NXBRPT0=--7f3c6a095def1a5b44ffd8c0869dc383d7476997; __cf_bm=H2NlHntDdN8vUo5pPM2S362SI5lXY4SPg0OamlMnp3s-1766933344-1.0.1.1-3HyX46X.nLww5W1v5ptGg53ttITV9KIro8WC.GHvPlSn9tZErijSxFUJVz1BJLuvzPAWBdwpLWBJVx.cGFmHckkM2Fcx0goORCeUHXNkQWc; _dd_s=rum=0&expire=1766934298150&logs=1&id=45866c15-03ec-4f79-b02e-7bc09e404b3e&created=1766929816686; _ga_TWGX3QNXGG=GS2.1.s1766929816$o10$g1$t1766933398$j59$l0$h461308641; cf_clearance=hiQVuoIS8lRxgfbH2L2IBYthHtjldgYx_EBVfU.AgsU-1766933405-1.2.1.1-e9IO8AFx.JlN9MIlugO.oDkiXPyuj50JlYKrLjNDJ6fvM9QkQcsIBlDbBsE.Bs1yZlwl4ctWKdOqH3IGeApSLt_MAg6Q4XhnrtKPuxfgxzLZM0VhFAgDl0Gosq.9krDzgBjkykyCW4IQTFADJEMByLG41F8rgUsIAfrYWUp9XpBbmOGohCzMjeHxR2xOoU1o31_grp4WEh6TBuDnG0mpe6p647bSema57xySLi0S12yUofznaWRDPZBzdPdnJeoi; session=a1e93babfc520a46269c99cb260c2060ac74b46575267d271dbaad012ca37a6a59095a15dac8420059333315d37e5542'
}

# --- 2. 鉴权与业务订阅包 ---

# 鉴权包 (带 Token)
AUTH_PACKET = {
    "type": "connection_init",
    "payload": {
        "accessToken": "a1e93babfc520a46269c99cb260c2060ac74b46575267d271dbaad012ca37a6a59095a15dac8420059333315d37e5542",
        "language": "zh",
        "lockdownToken": "s5MNWtjTM5TvCMkAzxov"
    }
}

# 基础环境包 (在线人数、余额、通知)
BASE_SUBS = [
    {"id": "90d5cbe1-df61-45d9-8dfd-c2b8deac8775", "type": "subscribe",
     "payload": {"query": "subscription OnlineCountSubscription {\n  onlineCount\n}", "variables": {}}},
    {"id": "b7fcf0d7-441d-4c03-8dfe-ea781811befe", "type": "subscribe", "payload": {
        "query": "subscription AvailableBalances {\n  availableBalances {\n    amount\n    identifier\n    balance { amount currency }\n  }\n}"}},
    {"id": "f4301dd8-1e64-4f7e-92b9-69a14c902ab8", "type": "subscribe", "payload": {"key": "1glfo72",
                                                                                    "query": "subscription Notifications($includeAffiliateData: Boolean = true) {\n  notifications { id type acknowledged }\n}",
                                                                                    "variables": {
                                                                                        "includeAffiliateData": True}}}
]

# 聊天室订阅请求 (Target)
CHAT_SUB = {"id": "3d94d7ee-dab0-4e4d-815b-b21bc92335cb", "type": "subscribe", "payload": {"key": "jiv4ay",
                                                                                           "query": "subscription ChatMessages($chatId: String!) {\n  chatMessages(chatId: $chatId) {\n    id\n    data {\n      __typename\n      ... on ChatMessageDataText { message }\n      ... on ChatMessageDataBot { message }\n    }\n    createdAt\n    user {\n      name\n      flags { flag }\n    }\n  }\n}",
                                                                                           "variables": {
                                                                                               "chatId": "96deb88b-ced9-4b78-b4da-8a65324c2aff"}}}

# 高额投注订阅请求
HIGHROLLER_BETS_SUB = {
    "id": "0764f28d-892d-46fd-80c5-3aeb77209e3b",
    "type": "subscribe",
    "payload": {
        "query": "subscription BetsBoard_HighrollerSportBets {\n  highrollerSportBets {\n    id\n    iid\n    bet {\n      ...BetsBoardSport_BetBet\n    }\n  }\n}\n\nfragment BetsBoardSport_BetBet on BetBet {\n  __typename\n  ... on SwishBet {\n    __typename\n    id\n    updatedAt\n    createdAt\n    potentialMultiplier\n    amount\n    currency\n    user {\n      id\n      name\n      preferenceHideBets\n    }\n    outcomes {\n      __typename\n      id\n      odds\n      outcome {\n        __typename\n        id\n        market {\n          id\n          competitor {\n            name\n          }\n          game {\n            id\n            fixture {\n              id\n              tournament {\n                id\n                category {\n                  id\n                  sport {\n                    id\n                    slug\n                  }\n                }\n              }\n            }\n          }\n        }\n      }\n    }\n  }\n  ... on SportBet {\n    __typename\n    id\n    updatedAt\n    createdAt\n    potentialMultiplier\n    amount\n    currency\n    user {\n      name\n      preferenceHideBets\n    }\n    outcomes {\n      id\n      odds\n      fixtureAbreviation\n      fixtureName\n      fixture {\n        id\n        tournament {\n          id\n          category {\n            id\n            sport {\n              id\n              slug\n            }\n          }\n        }\n      }\n    }\n  }\n  ... on RacingBet {\n    __typename\n    id\n    active\n    payout\n    updatedAt\n    createdAt\n    betPotentialMultiplier: potentialMultiplier\n    amount\n    currency\n    betStatus: status\n    payoutMultiplier\n    adjustments {\n      payoutMultiplier\n    }\n    user {\n      id\n      name\n      preferenceHideBets\n    }\n    outcomes {\n      id\n      type\n      derivativeType\n      prices {\n        marketName\n        odds\n      }\n      event {\n        meeting {\n          racing {\n            slug\n          }\n        }\n      }\n      selectionSlots {\n        runners {\n          name\n        }\n      }\n      result {\n        resultedPrices\n      }\n    }\n  }\n}"
    }
}


# --- 3. 消息处理与逻辑 ---

def on_message(ws, message):
    data = json.loads(message)

    # A. 鉴权确认
    if data.get("type") == "connection_ack":
        print("[系统] 身份认证成功。正在初始化环境...")
        # 发送基础包
        for sub in BASE_SUBS:
            ws.send(json.dumps(sub))
            time.sleep(0.1)
        # 发送聊天室订阅
        # print("[系统] 正在开启聊天室监听...")
        # ws.send(json.dumps(CHAT_SUB))
        # 发送高额投注订阅
        print("[系统] 正在开启高额投注监听...")
        ws.send(json.dumps(HIGHROLLER_BETS_SUB))
        # 开启心跳
        threading.Thread(target=heartbeat, args=(ws,), daemon=True).start()

    # B. 业务推送解析
    elif data.get("type") == "next":
        payload = data.get("payload", {}).get("data", {})

        # 1. 聊天室消息解析
        if "chatMessages" in payload:
            msg_node = payload["chatMessages"]
            user_node = msg_node.get("user") or {}

            # 提取字段
            user_name = user_node.get("name") or "未知用户"
            created_at = msg_node.get("createdAt")

            # 提取消息内容 (处理不同类型)
            data_node = msg_node.get("data") or {}
            message_text = data_node.get("message") or "[非文字消息]"

            # 提取等级标签 (如 bronze, platinum)
            flags = user_node.get("flags", [])
            level = flags[-1].get("flag") if flags else "无等级"

            # --- 格式化打印结果 ---
            print("-" * 70)
            print(f"⏰ 时间: {created_at}")
            print(f"👤 玩家: {user_name} (等级: {level})")
            print(f"💬 内容: {message_text}")
            print("-" * 70)

        # 2. 在线人数解析 (可选)
        elif "onlineCount" in payload:
            print(f"👥 当前在线人数: {payload['onlineCount']}")

        # 3. 高额投注解析
        elif "highrollerSportBets" in payload:
            bet_data = payload["highrollerSportBets"]
            if not bet_data:
                return
            
            bet_node = bet_data.get("bet", {})
            if not bet_node:
                return
            
            # 提取基础信息
            bet_id = bet_data.get("id") or bet_node.get("id") or "未知ID"
            bet_type = bet_node.get("__typename") or "未知类型"
            amount = bet_node.get("amount")
            currency = bet_node.get("currency", "USDT")
            potential_multiplier = bet_node.get("potentialMultiplier") or bet_node.get("betPotentialMultiplier")
            created_at = bet_node.get("createdAt")
            updated_at = bet_node.get("updatedAt")
            
            # 提取用户信息
            user_node = bet_node.get("user", {})
            user_name = user_node.get("name") or "未知用户"
            user_id = user_node.get("id")
            
            # 检查是否是重点关注用户
            is_monitored_user = user_name in FILTERED_USERS
            
            # 格式化金额
            amount_str = f"{amount:,.2f}" if amount else "N/A"
            
            # --- 格式化打印结果 ---
            print("=" * 70)
            # 如果是重点关注用户，添加感叹号标记
            if is_monitored_user:
                print(f"🎰 【高额投注】⚠️⚠️⚠️ {user_name} ⚠️⚠️⚠️")
            else:
                print(f"🎰 【高额投注】")
            print(f"⏰ 时间: {created_at or updated_at or '未知'}")
            print(f"👤 玩家: {user_name}" + (f" (ID: {user_id})" if user_id else ""))
            print(f"💰 金额: {amount_str} {currency}")
            if potential_multiplier:
                print(f"📈 潜在倍数: {potential_multiplier:.2f}x")
            print(f"📋 投注类型: {bet_type}")
            print(f"🆔 投注ID: {bet_id}")
            
            # 根据投注类型提取详细信息
            outcomes = bet_node.get("outcomes", [])
            if outcomes:
                print(f"📊 投注详情:")
                for idx, outcome in enumerate(outcomes, 1):
                    odds = outcome.get("odds")
                    if odds:
                        print(f"   {idx}. 赔率: {odds}")
                    
                    # SportBet 特有字段
                    if bet_type == "SportBet":
                        fixture_name = outcome.get("fixtureName")
                        fixture_abbr = outcome.get("fixtureAbreviation")
                        if fixture_name:
                            print(f"      比赛: {fixture_name}")
                        if fixture_abbr:
                            print(f"      缩写: {fixture_abbr}")
                    
                    # SwishBet 特有字段
                    elif bet_type == "SwishBet":
                        outcome_node = outcome.get("outcome", {})
                        market_node = outcome_node.get("market", {}) if outcome_node else {}
                        competitor_node = market_node.get("competitor", {}) if market_node else {}
                        competitor_name = competitor_node.get("name")
                        if competitor_name:
                            print(f"      队伍: {competitor_name}")
                        
                        game_node = market_node.get("game", {}) if market_node else {}
                        fixture_node = game_node.get("fixture", {}) if game_node else {}
                        tournament_node = fixture_node.get("tournament", {}) if fixture_node else {}
                        category_node = tournament_node.get("category", {}) if tournament_node else {}
                        sport_node = category_node.get("sport", {}) if category_node else {}
                        sport_slug = sport_node.get("slug")
                        if sport_slug:
                            print(f"      运动: {sport_slug}")
                    
                    # RacingBet 特有字段
                    elif bet_type == "RacingBet":
                        prices = outcome.get("prices", [])
                        for price in prices:
                            market_name = price.get("marketName")
                            price_odds = price.get("odds")
                            if market_name:
                                print(f"      市场: {market_name}" + (f" (赔率: {price_odds})" if price_odds else ""))
                        
                        event_node = outcome.get("event", {})
                        meeting_node = event_node.get("meeting", {}) if event_node else {}
                        racing_node = meeting_node.get("racing", {}) if meeting_node else {}
                        racing_slug = racing_node.get("slug")
                        if racing_slug:
                            print(f"      赛马类型: {racing_slug}")
                        
                        selection_slots = outcome.get("selectionSlots", [])
                        for slot in selection_slots:
                            runners = slot.get("runners", [])
                            for runner in runners:
                                runner_name = runner.get("name")
                                if runner_name:
                                    print(f"      赛马: {runner_name}")
            
            # RacingBet 特有状态信息
            if bet_type == "RacingBet":
                active = bet_node.get("active")
                payout = bet_node.get("payout")
                bet_status = bet_node.get("betStatus")
                payout_multiplier = bet_node.get("payoutMultiplier")
                if active is not None:
                    print(f"🔄 状态: {'活跃' if active else '非活跃'}")
                if bet_status:
                    print(f"📊 投注状态: {bet_status}")
                if payout:
                    print(f"💵 派彩: {payout} {currency}")
                if payout_multiplier:
                    print(f"📈 派彩倍数: {payout_multiplier:.2f}x")
            
            print("=" * 70)


def heartbeat(ws):
    while ws.sock and ws.sock.connected:
        try:
            ws.send(json.dumps({"type": "ping"}))
            time.sleep(20)
        except:
            break


def on_open(ws):
    print("[系统] WebSocket 已连接，正在发送鉴权包...")
    ws.send(json.dumps(AUTH_PACKET))


def on_error(ws, error):
    print(f"[错误] {error}")


def on_close(ws, status, msg):
    print("[系统] 连接断开，3秒后重连...")
    time.sleep(3)
    start_ws()


def start_ws():
    ws = websocket.WebSocketApp(
        WS_URL,
        header=HEADERS,
        subprotocols=["graphql-transport-ws"],
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()


if __name__ == "__main__":
    start_ws()