import streamlit as st
import pandas as pd
import time
import os
import math
import re
import random
import requests
import shutil 

st.set_page_config(page_title="AI 맛집 랭킹 (Cloud Fix)", page_icon="☁️", layout="wide")

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ... (1. 도구 설정 및 RecommendationEngine 클래스는 이전과 동일하므로 생략하지 않고 전체 코드 제공) ...

def get_lat_lon(address):
    VWORLD_API_KEY = "05B55DB4-5776-37FB-B555-BE393DE47184" 
    try:
        clean_addr = address.split("(")[0].strip()
        url = "http://api.vworld.kr/req/address?"
        params = {
            "service": "address", "request": "getcoord", "version": "2.0",
            "crs": "epsg:4326", "address": clean_addr, "refine": "true",
            "simple": "false", "format": "json", "type": "ROAD", "key": VWORLD_API_KEY
        }
        response = requests.get(url, params=params, timeout=2)
        data = response.json()
        if data['response']['status'] == 'OK':
            return float(data['response']['result']['point']['y']), float(data['response']['result']['point']['x'])
        else:
            params['type'] = 'PARCEL'
            response = requests.get(url, params=params, timeout=2)
            data = response.json()
            if data['response']['status'] == 'OK':
                return float(data['response']['result']['point']['y']), float(data['response']['result']['point']['x'])
    except: return None, None
    return None, None

class RecommendationEngine:
    def __init__(self):
        self.priority_keywords = {
            "맛 (기본)": ["존맛", "맛집", "맛있", "최고", "인생"],
            "가성비": ["가성비", "저렴", "착한", "가격", "양 많", "무한리필"],
            "양/푸짐함": ["양 많", "푸짐", "배부", "리필", "든든", "서비스"],
            "주차/편의성": ["주차", "발렛", "역세권", "편하", "엘리베이터", "넓은"],
            "친절/청결": ["친절", "깨끗", "청결", "위생", "화장실", "매너"],
            "사진/인스타": ["사진", "인테리어", "뷰", "감성", "플레이팅", "조명", "예쁜"]
        }

    def calculate_score(self, row, user_priority):
        try: visitor = int(row['visitor_reviews'])
        except: visitor = 0
        try: blog = int(row['blog_reviews'])
        except: blog = 0
        
        total_reviews = visitor + blog
        base_score = math.log(total_reviews + 1) * 10
        match_score = 0
        tags = str(row['tags'])
        matched_tags = []
        
        target_keywords = self.priority_keywords.get(user_priority, [])
        for keyword in target_keywords:
            if keyword in tags:
                match_score += 100
                matched_tags.append(f"#{keyword}")

        final_score = int(base_score + match_score)
        matched_tags = list(set(matched_tags))
        return final_score, matched_tags, total_reviews

def clean_menu_text(name_raw, price_raw):
    price = re.sub(r"[^0-9,]", "", price_raw) + "원"
    name = name_raw
    remove_words = ["대표", "인기", "추천", "BEST", "HIT", "시그니처", "NEW", "메인"]
    for word in remove_words: name = name.replace(word, "")
    name = re.sub(r"^[\s:.\-]+|[\s:.\-]+$", "", name)
    if ":" in name: name = name.split(":")[0]
    if "\n" in name: name = name.split("\n")[0]
    name = re.sub(r"\(.*?\)", "", name)
    if len(name) > 20: name = " ".join(name.split()[:3])
    return f"{name.strip()}: {price}"

def collect_data_to_csv(location, category, max_items):
    options = Options()
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)

    service = None
    linux_paths = ["/usr/bin/chromedriver", "/usr/bin/chromium-driver", "/usr/lib/chromium-browser/chromedriver"]
    for path in linux_paths:
        if os.path.exists(path):
            service = Service(path)
            break
    if service is None:
        if os.path.exists("chromedriver.exe"): service = Service("chromedriver.exe")
        else:
            try: service = Service(ChromeDriverManager().install())
            except: pass

    try:
        if service: driver = webdriver.Chrome(service=service, options=options)
        else: return "🚨 크롬 드라이버를 찾을 수 없습니다."
    except Exception as e: return f"🚨 드라이버 실행 오류: {e}"

    wait = WebDriverWait(driver, 20)
    
    status_text = st.empty()
    progress_bar = st.progress(0)
    data_list = []
    
    try:
        driver.get("https://map.naver.com/")
        st.toast("서버에서 지도 접속 중...", icon="☁️")
        time.sleep(2)

        try:
            search_box = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".input_search")))
            time.sleep(1)
            keyword = f"{location} {category}"
            search_box.click()
            time.sleep(0.5)
            for char in keyword:
                search_box.send_keys(char)
                time.sleep(random.uniform(0.05, 0.1))
            time.sleep(0.5)
            search_box.send_keys(Keys.ENTER)
            st.toast("검색어 입력 완료...", icon="🔍")
            time.sleep(3) 
        except Exception as e: return f"❌ 검색 오류: {e}"

        frame_found = False
        for _ in range(3):
            try:
                driver.switch_to.default_content()
                wait.until(EC.presence_of_element_located((By.ID, "searchIframe")))
                driver.switch_to.frame("searchIframe")
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".UEzoS, .place_bluelink")))
                frame_found = True
                break
            except: time.sleep(2)
        
        if not frame_found: return "❌ 목록을 찾을 수 없습니다."

        for _ in range(int(max_items / 5) + 2):
            driver.execute_script("window.scrollBy(0, 10000);")
            time.sleep(0.5)

        stores = driver.find_elements(By.CSS_SELECTOR, ".UEzoS")
        if not stores: stores = driver.find_elements(By.CSS_SELECTOR, ".place_bluelink")
        
        scan_limit = min(len(stores), max_items)
        collected_count = 0
        
        for i in range(len(stores)):
            if collected_count >= max_items: break
            progress_bar.progress(min((collected_count + 1) / max_items, 1.0))
            
            # 1. 데이터 저장용 그릇 미리 준비 (실패해도 이거라도 저장하려고)
            item_data = {
                "name": "알수없음",
                "category": "음식점",
                "visitor_reviews": 0,
                "blog_reviews": 0,
                "address": location,
                "hours": "정보 없음",
                "parking": "정보 없음",
                "menus": "메뉴 정보 없음",
                "tags": "",
                "lat": None,
                "lon": None
            }

            try:
                driver.switch_to.default_content()
                driver.switch_to.frame("searchIframe")
                
                stores = driver.find_elements(By.CSS_SELECTOR, ".UEzoS")
                if not stores: stores = driver.find_elements(By.CSS_SELECTOR, ".place_bluelink")
                store_container = stores[i]
                
                if "광고" in store_container.text[:50]: continue

                click_target = None
                try: click_target = store_container.find_element(By.CSS_SELECTOR, ".tzwk0")
                except:
                    try: click_target = store_container.find_element(By.CSS_SELECTOR, ".TYaxT")
                    except: click_target = store_container

                name = click_target.text
                item_data["name"] = name
                status_text.text(f"탐색 중 ({collected_count+1}/{max_items}): {name}")
                
                driver.execute_script("arguments[0].scrollIntoView(true);", click_target)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", click_target)
                time.sleep(1.5) 
                
                # 상세 페이지 진입 시도
                driver.switch_to.default_content()
                try:
                    wait.until(EC.presence_of_element_located((By.ID, "entryIframe")))
                    driver.switch_to.frame("entryIframe")
                    
                    # --- 여기서부터는 실패해도 무시하고(pass) 넘어갑니다 ---
                    page_source = driver.page_source
                    
                    try:
                        v_match = re.search(r"방문자 리뷰\s*<[^>]+>\s*([\d,]+)", page_source)
                        if not v_match: v_match = re.search(r"방문자 리뷰\s*([\d,]+)", page_source)
                        if v_match: item_data["visitor_reviews"] = int(v_match.group(1).replace(",", ""))
                    except: pass

                    try:
                        b_match = re.search(r"블로그 리뷰\s*<[^>]+>\s*([\d,]+)", page_source)
                        if not b_match: b_match = re.search(r"블로그 리뷰\s*([\d,]+)", page_source)
                        if b_match: item_data["blog_reviews"] = int(b_match.group(1).replace(",", ""))
                    except: pass
                    
                    try: 
                        c_match = re.search(r"<span class=\"LnJFt\">([^<]+)</span>", page_source)
                        if c_match: item_data["category"] = c_match.group(1)
                    except: pass
                    
                    try:
                        a_match = re.search(r"<span class=\"LDgIH\">([^<]+)</span>", page_source)
                        if a_match: item_data["address"] = a_match.group(1)
                    except: pass
                    
                    try: item_data["hours"] = driver.find_element(By.CSS_SELECTOR, ".U7pYf").text
                    except: pass
                    
                    try:
                        body_text = driver.find_element(By.TAG_NAME, "body").text
                        if "주차 가능" in body_text or "주차가능" in body_text: item_data["parking"] = "✅ 주차 가능"
                        elif "주차 불가" in body_text: item_data["parking"] = "❌ 주차 불가"
                        elif "발렛" in body_text: item_data["parking"] = "🚗 발렛/주차 가능"
                        elif "주차" in body_text: item_data["parking"] = "✅ 주차 가능"
                    except: pass

                    try:
                        m_names = driver.find_elements(By.CSS_SELECTOR, ".lPzHi")
                        m_prices = driver.find_elements(By.CSS_SELECTOR, ".GXS1X")
                        extracted = []
                        if m_names and m_prices:
                            for k in range(min(len(m_names), len(m_prices), 5)):
                                extracted.append(clean_menu_text(m_names[k].text, m_prices[k].text))
                        if not extracted:
                            menu_tab = driver.find_elements(By.XPATH, "//span[text()='메뉴']")
                            if menu_tab:
                                driver.execute_script("arguments[0].click();", menu_tab[0])
                                time.sleep(0.5)
                                m_names = driver.find_elements(By.CSS_SELECTOR, ".lPzHi")
                                m_prices = driver.find_elements(By.CSS_SELECTOR, ".GXS1X")
                                if m_names and m_prices:
                                    for k in range(min(len(m_names), len(m_prices), 5)):
                                        extracted.append(clean_menu_text(m_names[k].text, m_prices[k].text))
                        if not extracted:
                            body_txt = driver.find_element(By.TAG_NAME, "body").text
                            lines = body_txt.split('\n')
                            for k, line in enumerate(lines):
                                if re.search(r"^\d{1,3}(,\d{3})*원$", line.strip()):
                                    if k > 0 and len(lines[k-1]) < 20:
                                        extracted.append(clean_menu_text(lines[k-1], line))
                                    if len(extracted) >= 3: break
                        if extracted: item_data["menus"] = " | ".join(extracted)
                    except: pass

                    try:
                        t_matches = re.findall(r"<span class=\"Tfd3t\">([^<]+)</span>", page_source)
                        if t_matches: item_data["tags"] = ", ".join(t_matches[:5])
                    except: pass
                    
                    item_data["lat"], item_data["lon"] = get_lat_lon(item_data["address"])

                except:
                    # 상세 페이지 진입 실패해도 목록에서 얻은 이름으로 저장
                    pass
                
                # [성공] 어떤 경우에도 리스트에 추가하고 카운트 올림
                data_list.append(item_data)
                collected_count += 1
                status_text.text(f"✅ 저장 완료 ({collected_count}/{max_items}): {item_data['name']}")
                
            except Exception: 
                # 클릭조차 실패한 경우만 건너뜀
                pass
            
    except Exception as e: return f"🚨 에러 발생: {e}"
    finally:
        driver.quit() 
        status_text.empty()
        progress_bar.empty()
    
    if data_list:
        df = pd.DataFrame(data_list)
        df.to_csv("my_restaurants.csv", index=False, encoding="utf-8-sig")
        return f"✅ {len(data_list)}개 저장 완료!"
    else: return "❌ 데이터 수집 실패."

# ==========================================
# 3. UI 화면
# ==========================================

st.title("🍽️ AI 맛집 랭킹 (Cloud)")

with st.sidebar:
    st.header("🛠️ 데이터 수집기")
    c_loc = st.text_input("지역", value="공주시")
    c_cat = st.text_input("메뉴", value="한식")
    c_qty = st.slider("수집 개수", 10, 50, 10)
    if st.button("📥 데이터 수집 시작", type="primary"):
        if os.path.exists("my_restaurants.csv"): os.remove("my_restaurants.csv")
        with st.spinner("서버에서 수집 중입니다..."):
            msg = collect_data_to_csv(c_loc, c_cat, c_qty)
            if "성공" in msg:
                st.success(msg)
                time.sleep(1)
                st.rerun()
            else: st.error(msg)

if not os.path.exists("my_restaurants.csv"):
    st.info("👈 왼쪽 사이드바에서 [데이터 수집 시작] 버튼을 눌러주세요.")
else:
    try:
        df = pd.read_csv("my_restaurants.csv")
        
        def analyze_status(hours_str):
            if pd.isna(hours_str) or hours_str == "정보 없음": return "❓ 정보없음"
            text = hours_str.replace("\n", " ")
            if "영업 중" in text or "24시간 영업" in text: return "✅ 영업중"
            elif "곧 영업 종료" in text or "라스트오더" in text: return "⚠️ 곧마감"
            elif "영업 종료" in text or "휴무" in text or "영업 전" in text or "브레이크타임" in text or "영업 시작" in text: return "❌ 영업종료"
            else: return "❓ 확인필요"

        df['status'] = df['hours'].apply(analyze_status)
        
        def get_min_price(menu_str):
            if pd.isna(menu_str) or menu_str == "메뉴 정보 없음": return 999999
            try:
                first_menu = menu_str.split(" | ")[0]
                price_match = re.search(r"(\d{1,3}(?:,\d{3})*)", first_menu)
                if price_match: return int(price_match.group(1).replace(",", ""))
            except: pass
            return 999999

        df['min_price'] = df['menus'].apply(get_min_price)

        # --- 필터 ---
        st.markdown("### 🔍 필터 & 정렬")
        col_sort, col_type, col_opt = st.columns([1.5, 1.5, 1])
        with col_sort:
            sort_option = st.radio("정렬 기준", ["🏆 랭킹순 (추천)", "💰 가격순 (저렴한 순)"], horizontal=True)
        with col_type:
            filter_type = st.radio("업종 구분", ["전체 보기", "🍚 식사만", "☕ 카페만"], horizontal=True)
        with col_opt:
            st.write(""); only_open = st.checkbox("✅ 영업 중", value=False)
            only_parking = st.checkbox("🅿️ 주차 가능", value=False)

        cafe_keywords = "카페|커피|디저트|베이커리|케이크|찻집|Tea|espresso|브런치"
        if filter_type == "🍚 식사만": df = df[~df['category'].str.contains(cafe_keywords, case=False, na=False)]
        elif filter_type == "☕ 카페만": df = df[df['category'].str.contains(cafe_keywords, case=False, na=False)]

        if only_open: df = df[df['status'].isin(["✅ 영업중", "⚠️ 곧마감"])]
        if only_parking: df = df[df['parking'].str.contains("가능|발렛", na=False)]

        st.caption(f"검색 결과: {len(df)}개")
        
        map_data = df[df['lat'].notnull() & df['lon'].notnull()]
        if not map_data.empty:
            with st.expander("🗺️ 지도로 위치 보기 (클릭)", expanded=True):
                avg_lat = map_data['lat'].mean()
                avg_lon = map_data['lon'].mean()
                m = folium.Map(location=[avg_lat, avg_lon], zoom_start=13)
                for _, item in map_data.iterrows():
                    color = "blue" if "영업중" in item['status'] else "red"
                    icon = "coffee" if "카페" in item['category'] or "커피" in item['category'] else "cutlery"
                    folium.Marker(
                        [item['lat'], item['lon']],
                        popup=f"<b>{item['name']}</b><br>{item['status']}",
                        tooltip=item['name'],
                        icon=folium.Icon(color=color, icon=icon, prefix='fa')
                    ).add_to(m)
                st_folium(m, width="100%", height=400)
        
        st.divider()

        engine = RecommendationEngine()
        results = []
        for index, row in df.iterrows():
            score, matched_tags, total = engine.calculate_score(row, "맛 (기본)")
            item = row.to_dict()
            item['final_score'] = score
            item['match_reason'] = matched_tags
            item['total_reviews'] = total
            results.append(item)
        
        if "가격순" in sort_option: results.sort(key=lambda x: x['min_price'])
        else: results.sort(key=lambda x: x['final_score'], reverse=True)
        
        for idx, item in enumerate(results):
            emoji = "🥇" if idx == 0 else "🥈" if idx == 1 else "🥉" if idx == 2 else f"{idx+1}위"
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    title_md = f"### {emoji} {item['name']}"
                    if "영업중" in item['status']: status_badge = f":green[[{item['status']}]]"
                    elif "영업종료" in item['status']: status_badge = f":red[[{item['status']}]]"
                    else: status_badge = f":orange[[{item['status']}]]"
                    st.markdown(f"{title_md} &nbsp; {status_badge}")
                    
                    parking_info = item.get('parking', '정보 없음')
                    if "가능" in parking_info: st.caption(f"🅿️ {parking_info}")
                    
                    if pd.notnull(item['menus']) and item['menus'] != "메뉴 정보 없음":
                        menu_list = item['menus'].split(" | ")
                        first_menu = menu_list[0]
                        extra_count = len(menu_list) - 1
                        if extra_count > 0: st.markdown(f"**🍱 대표메뉴:** {first_menu} (외 {extra_count}개)")
                        else: st.markdown(f"**🍱 대표메뉴:** {first_menu}")
                    else: st.caption("🍱 메뉴 정보 없음")
                    
                    if item['match_reason']:
                        st.caption(f"💡 추천: {', '.join(item['match_reason'])}")

                with c2:
                    st.metric("총 리뷰", f"{item['total_reviews']}", f"블로그 {item['blog_reviews']}")
                
                with st.expander("📍 상세 정보 & 전체 메뉴 보기"):
                    if pd.notnull(item['menus']) and item['menus'] != "메뉴 정보 없음":
                        st.markdown("#### 📜 전체 메뉴판")
                        for m in item['menus'].split(" | "):
                            st.write(f"- {m}")
                        st.markdown("---")
                    st.write(f"**주소:** {item['address']}")
                    st.write(f"**영업시간:** {item['hours']}")
                    st.write(f"**주차:** {item.get('parking', '정보 없음')}")
                    st.write(f"**카테고리:** {item['category']}")
                    if pd.notnull(item['tags']):
                        st.info(f"태그: {item['tags']}")

    except Exception as e:
        st.error(f"데이터 파일 읽기 오류: {e}")
