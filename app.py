from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, QuickReply, QuickReplyButton, MessageAction
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# 從環境變數取得 Channel Access Token 和 Channel Secret
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
line_handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# 設定 Google Gemini API
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
genai.configure(api_key=GOOGLE_API_KEY)

# 設定 Gemini 模型
generation_config = {
    "temperature": 0.7,
    "top_p": 0.8,
    "top_k": 40,
    "max_output_tokens": 2000,
}

safety_settings = [
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
    },
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
    },
]

# 律師人格設定
LAWYER_SYSTEM_PROMPT = """你是律師，一位擁有20年經驗的台灣家事法律專業律師，專精於：

1. 離婚案件（協議離婚、裁判離婚）
2. 夫妻財產分配（剩餘財產分配請求權）
3. 子女監護權（親權）與會面交往權
4. 扶養費與贍養費
5. 家庭暴力防治與保護令
6. 繼承相關家事問題

請以以下風格回應：
- 專業權威但溫暖同理
- 引用台灣民法親屬編相關法條
- 提供具體法律程序建議
- 強調「每個案件情況不同，建議尋求專業律師評估」
- 對於急迫危險情況提供緊急協助資訊

重要格式：
1. 開頭先說「您好！我是AI婚姻法律諮詢小幫手」
2. 分析法律要件和實務見解
3. 提供具體建議步驟
4. 結尾提醒諮詢專業律師
5. 必要時提供相關資源連結
6. 總字數不超過300字

切記：不提供絕對成敗預測，保持法律專業的謹慎態度。

每次回答結束前都要加上：
※ 本回答僅供參考，具體個案請尋求專業律師協助 ※
"""

# 本地預設問答庫（擴充至20+個問題）
LOCAL_QA = {
    # 財產分配類
    "房子是婚後買的但登記在對方名下，離婚時我可以分嗎？": "當夫妻在婚姻關係存續期間共同繳納房貸購買房產時，這類房產通常被視為雙方的共同財產，房產權利的認定會依照雙方的出資比例來確定各自的持分。\n\n若是共同夫妻雙方共同繳納房貸的情況下，在離婚時進行財產分配，通常會先就雙方實際繳付的房貸金額進行平均分配，再討論如何切割房產或進行處分。一般而言，繳納越多房貸，相當於持有較高的房產比例。\n\n#房子#財產#分配\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",
    
    "對方外遇，我可以請求什麼賠償？怎麼搜集外遇的證據？": "「侵害配偶權」是婚姻一方違反了與其配偶身份相關的權利和義務，例如：一方婚內出軌的行為，破壞了夫妻間應有的互相忠誠義務，可以被視為侵害配偶權。現行法律實務上，法院會依民法第184條侵權行為及第195條規定作為審理侵害配偶權的依據。\n\n對於侵害配偶權的證據，不必需要確鑿之發生性行為證明。只需提供足以表明配偶與第三者之間存在超過普通友誼範疇的行為證明，例如：照片、影片、訊息對話記錄、社交媒體發文或留言的截圖、旅館信用卡交易記錄、錄音檔案等。只要是足以證明超過一般朋友關係的證據，都有機會用來佐證侵害配偶權。\n\n#外遇#賠償#證據\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",
    
    "離婚的財產要怎麼分配？": "「剩餘財產差額分配」並非將夫妻所有財產加總除以二，而是針對「婚後累積之財產」進行「差額」的平均分配。（民法第1030條之一～民法第1030條之三）\n計算公式三步驟：\n結算夫的剩餘財產： （夫的婚後財產 - 夫的婚後債務）。若結果為負數，以零計算。\n結算妻的剩餘財產： （妻的婚後財產 - 妻的婚後債務）。若結果為負數，以零計算。\n分配差額： （剩餘財產較多方 - 剩餘財產較少方）÷ 2 = 較少方可請求之金額。\n\n特別注意：負債不分配原則 若一方婚後負債大於資產（例如夫欠債500萬，資產僅100萬），其剩餘財產視為「零」，而非負400萬。因此，妻不需要分擔夫的債務，但夫也無法向妻請求分配\n\n#財產#分配#離婚\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",
    
    "對方如果有欠很多債，我要幫他還債嗎？這會影響夫妻離婚財產分配嗎？": "如果對方欠債是沒有義務幫他還債，同時也不會影響夫妻離婚財產分配，因為夫妻在離婚時會去釐清債務性質，一共有下列兩種：\n共同債務：用於家庭生活，夫妻雙方需共同承擔。\n個人債務：如個人投資、賭債，則無須由配偶負責。\n一般而言，夫妻在婚姻關係中產生的共同債務，例如房貸、生活開銷，雙方都有義務承擔，但如果屬於個人負債債務，像是如投資失敗、賭債，則由欠債方自行負責。\n\n#欠債#財產#分配#離婚\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",
    
    "離婚很久了，還可以回來要財產嗎？": "只要在離婚時沒有放棄「婚後財產分配」這個權利，那麼在之後只要在發現對方有更多剩餘財產的 2 年內，就可以提出分配請求。\n這個 2 年的限制，是為了保護婚後財產比較少的人，不會因為不知道而錯過權利；同時也避免財產比較多的一方一直處於不確定中。只要在 2 年內提出，就是合法、有效的請求。\n\n#離婚#財產#分配#很久\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",
    
    "離婚時發現對方脫產，怎麼辦？": "離婚時如果發現對方有脫產行為，只要夫妻一方在法定財產制結束前5年內，為了減少離婚後要分給另一方的剩餘財產而故意把婚後財產移轉出去（不包含履行道德上義務的合理贈與），那麼在請求剩餘財產分配時，這些被惡意移走的財產都可以「加回來」視為仍然存在的婚後財產，另一方仍然可以要求分配其中的一半，不會因為對方脫產而失去自己的權益。（民法第1030條之三）\n\n#惡意#財產#離婚#分配\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",

    # 子女監護類
    "法院如何決定小孩判給誰？在爭取小孩監護權（親權），經濟條件好的一方一定會贏嗎？": "夫妻共同決定由一方或雙方取得監護權，如果無法達成共識就由法院調解或裁判（民法第1055條第1項）。法院依子女的最佳利益決定由誰取得監護權，判斷標準包含父母與子女的年齡、健康、意願，以及子女的需求和父母是否能滿足這些需求。經濟條件確實是其中的考量，但非唯一（民法第1055條之1第1項）。\n\n#離婚#監護權#親權\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",
    
    "離婚後覺得對方帶不好，可以把監護權搶回來嗎？": "離婚後若對方有監護權卻未盡責，可以請法院重新指定監護人（民法第1055條第3項）。\n\n#離婚#監護權\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",
    
    "如果小孩判給另外一半，我可以去看他嗎（探視權）？": "原則上法院不會剝奪沒有監護權的父母探視子女的權利，但如果見面會妨害子女利益就可以限制或不允許探視（民法第1055條第5項）。\n\n#探視權\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",
    
    "如果離婚的話，一方經濟較弱勢，同時又要扶養小孩，我可以請求扶養贍養費嗎？可以請求多少？": "夫妻無過失的一方因離婚而生活有困難可以要求贍養費（民法第1057條），但贍養費不包含未成年子女的扶養費，父母就算離婚仍皆有扶養未成年子女的義務（民法第1116條之2）。\n\n#贍養費#扶養費#離婚\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",
    
    "如果要問小孩跟誰的意願，小孩Ｘ歲法官採納嗎？": "基本上只要未成年子女有表達意見之能力 ，主觀上有表達意見的意願，客觀上有向法院表達意見之可能。\n\n除下方四點例外情形，法院不得讓其表達。\n情況急迫，來不及讓子女陳述\n子女年紀年齡過小，尚無表達意見的能力\n子女現在所在不明，事實上無法讓其陳述\n依個案判斷子女之陳述顯不相當\n\n#監護權#子女意願#表達能力\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",

    # 家暴保護類
    "如果我被家暴的話，我要怎麼處理？": "首先，應優先保護自己與小孩的安全，可用手臂護住頭部、軀幹等重要部位，這不僅能降低受傷程度，也有助於之後驗傷時留下明確傷痕。接著，立即撥打 110 或 113 報案，讓警方或社工人員到場，藉此制止施暴者，避免情況惡化，防止更嚴重的傷害發生。此外，務必保全證據，包括到醫院驗傷、向警方或所在地派出所通報，並可進一步申請保護令，以確保自身安全並獲得法律上的保護。\n\n#家暴#保護令#110#113\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",
    
    "如果家暴的話，離婚會獲得更多補償嗎？": "因受家暴而判決離婚，對方屬於婚姻有過失的一方，\n如果受有財產上的損害，可以請求損害賠償。對於非財產上的損害，可請求慰撫金。\n如果有因此陷於生活困難時，也可向對方請求贍養費。\n（民法1056條）\n\n#家暴#離婚#損害賠償#贍養費\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",
    
    "如果對方沒有動手打我，只是言語辱罵、精神折磨，這樣也能算家暴嗎？": "算，精神暴力也是家暴，家庭暴力不限於肢體傷害，實施、精神或經濟上之騷擾、控制、脅迫，像是長期的言語羞辱、謾罵、恐嚇威脅、情緒勒索，甚至不給生活費、嚴格控管每一筆開銷等，都屬於家庭暴力的範疇。（家庭暴力防治法第二條）\n\n#家暴#言語污辱#精神折磨\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",
    
    "如果申請家暴保護令，他會知道我現在住在哪裡嗎？": "《家庭暴力防治法》有特別的保密機制。若您有住居所保密需求，可以在聲請狀中明確敘明，並提供一個替代的送達地址，例如親友家、工作地點或社福機構。\n法院會以秘密方式訊問，並將相關資料密封，禁止閱覽，以保護您的住居所資訊不被施暴者知悉。\n\n#家暴#保護令#保密\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",

    # 離婚程序類
    "想離婚怎麼辦？（離婚的步驟）": "協議離婚：只要夫妻雙方針對離婚和相關條件能達成共識，並找到兩個證人親自向雙方確認離婚的意思，便能簽立離婚協議書，由雙方一起持協議書和相關證件到戶政事務所登記。\n\n調解離婚：調解會在法院的調解室進行，由法院安排的調解委員居中協調，夫妻雙方可就離婚及相關事項進行協商。若最終調解成立，法院會製作「調解筆錄」並寄送給雙方，這份調解筆錄與法院判決有同等效力。\n\n裁判離婚：起訴→調解→開庭審理→收到判決。若調解不成立，便進入訴訟程序，法院會依據案件進行審理。\n\n#離婚方式#調解#裁判#法院#協議\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",
    
    "打一場離婚官司要花多少錢？": "主要分為「法院訴訟裁判費」和「律師費」\n\n法院訴訟裁判費：訴訟費用由提起離婚訴訟之一方先行繳納，若只有單純請求離婚，並無未成年子女監護權的請求，裁判費為4,500元；如果有未成年子女監護權的訴求，則須多支付1,500元，繳納之裁判費共6,000元。\n\n律師費：離婚案件通常以「審級」計費。依目前家事案件的市場行情，一審律師費用約在 8 萬至 10 萬元新台幣之間。若案情複雜或需跨縣市出庭，費用可能更高。\n\n#訴訟費#律師費#離婚官司\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",
    
    "如果我沒錢請律師怎麼辦？可以申請「法律扶助」嗎？": "可以申請免費律師，但需通過資力審查，也就是收入與財產資產低於一定標準。\n\n#法律扶助#沒錢#離婚#律師\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",
    
    "可以直接告離婚嗎？還是一定要先調解？（離婚程序）": "由於離婚訴訟為強制調解案件，在進入訴訟程序之前，法院會先安排調解程序，若調解不成，才會進入法院裁判離婚。\n\n#調解#直接離婚#法院#裁判\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",

    # 離婚條件類
    "在什麼樣的情況下，我可以離婚？": "民法第1052條第1項列舉多種離婚事由，包括：重婚、與配偶以外之人合意性交、不堪同居之虐待、惡意遺棄、意圖殺害他方、重大不治之惡疾、重大不治之精神病、生死不明已逾三年、因故意犯罪經判處有期徒刑逾六個月確定等。\n\n以及民法1052條第2項「難以維持婚姻重大事由」。\n\n#離婚#虐待#家暴#惡意\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※",
    
    "分居可以離婚嗎？分居多久可以離婚？": "台灣並沒有「分居自動離婚」的規定，不論分居多久，只要沒有辦理離婚登記，婚姻關係依然存在。\n然而「長期分居」可以作為證明婚姻破裂、難以維持的證據（民法第 1052 條第 2 項重大事由），但仍需由法院進行判決，並不會分居時間一到就自動生效。\n\n#分居#離婚#法院\n\n※ 本回答僅供參考，具體個案請尋求專業律師協助 ※"
}

# 快速回覆選項
QUICK_REPLY_ITEMS = [
    QuickReplyButton(action=MessageAction(label="離婚程序", text="請問協議離婚和裁判離婚有什麼不同？")),
    QuickReplyButton(action=MessageAction(label="財產分配", text="離婚時財產應該怎麼分配？")),
    QuickReplyButton(action=MessageAction(label="子女監護權", text="子女監護權的判定標準是什麼？")),
    QuickReplyButton(action=MessageAction(label="家暴求助", text="遭遇家庭暴力該怎麼辦？")),
    QuickReplyButton(action=MessageAction(label="法律扶助", text="如何申請法律扶助？"))
]

def is_legal_related(message):
    """簡單判斷是否與法律相關"""
    legal_keywords = ['離婚', '結婚', '財產', '監護', '贍養', '扶養', '家暴', '暴力', '律師', '法律', '訴訟', '法院', '判決', '協議', '權利', '義務', '賠償', '賠償金', '精神', '虐待', '外遇', '探視', '保護令', '裁判', '調解', '分居']
    return any(keyword in message for keyword in legal_keywords)

def get_local_answer(user_message):
    """檢查是否有本地預設答案"""
    # 精確匹配
    if user_message in LOCAL_QA:
        return LOCAL_QA[user_message]
    
    # 模糊匹配 - 檢查關鍵字
    clean_user_msg = user_message.replace('？', '').replace('?', '').replace('，', '').replace(',', '').replace(' ', '')
    
    # 財產分配相關問題
    if any(keyword in clean_user_msg for keyword in ['房子', '婚後', '登記', '分房']):
        if '婚後' in clean_user_msg and ('房子' in clean_user_msg or '房產' in clean_user_msg):
            return LOCAL_QA["房子是婚後買的但登記在對方名下，離婚時我可以分嗎？"]
    
    if any(keyword in clean_user_msg for keyword in ['外遇', '出軌', '小三', '外遇證據']):
        if '外遇' in clean_user_msg and ('賠償' in clean_user_msg or '證據' in clean_user_msg):
            return LOCAL_QA["對方外遇，我可以請求什麼賠償？怎麼搜集外遇的證據？"]
    
    if any(keyword in clean_user_msg for keyword in ['財產分配', '財產怎麼分', '剩餘財產']):
        return LOCAL_QA["離婚的財產要怎麼分配？"]
    
    if any(keyword in clean_user_msg for keyword in ['欠債', '還債', '債務']):
        return LOCAL_QA["對方如果有欠很多債，我要幫他還債嗎？這會影響夫妻離婚財產分配嗎？"]
    
    if any(keyword in clean_user_msg for keyword in ['脫產', '轉移財產']):
        return LOCAL_QA["離婚時發現對方脫產，怎麼辦？"]
    
    if any(keyword in clean_user_msg for keyword in ['很久', '後來', '事後']):
        if '財產' in clean_user_msg and '離婚' in clean_user_msg:
            return LOCAL_QA["離婚很久了，還可以回來要財產嗎？"]
    
    # 子女監護相關問題
    if any(keyword in clean_user_msg for keyword in ['監護權', '親權', '小孩判給誰']):
        if '經濟' in clean_user_msg or '條件' in clean_user_msg:
            return LOCAL_QA["法院如何決定小孩判給誰？在爭取小孩監護權（親權），經濟條件好的一方一定會贏嗎？"]
        return LOCAL_QA["法院如何決定小孩判給誰？在爭取小孩監護權（親權），經濟條件好的一方一定會贏嗎？"]
    
    if any(keyword in clean_user_msg for keyword in ['搶回來', '改定', '監護權改變']):
        return LOCAL_QA["離婚後覺得對方帶不好，可以把監護權搶回來嗎？"]
    
    if any(keyword in clean_user_msg for keyword in ['探視權', '看小孩', '探望']):
        return LOCAL_QA["如果小孩判給另外一半，我可以去看他嗎（探視權）？"]
    
    if any(keyword in clean_user_msg for keyword in ['贍養費', '扶養費', '生活費']):
        return LOCAL_QA["如果離婚的話，一方經濟較弱勢，同時又要扶養小孩，我可以請求扶養贍養費嗎？可以請求多少？"]
    
    if any(keyword in clean_user_msg for keyword in ['小孩意願', '法官採納', '幾歲']):
        return LOCAL_QA["如果要問小孩跟誰的意願，小孩Ｘ歲法官採納嗎？"]
    
    # 家暴保護相關問題
    if any(keyword in clean_user_msg for keyword in ['家暴處理', '被家暴', '家暴怎麼辦']):
        return LOCAL_QA["如果我被家暴的話，我要怎麼處理？"]
    
    if any(keyword in clean_user_msg for keyword in ['家暴補償', '家暴賠償']):
        return LOCAL_QA["如果家暴的話，離婚會獲得更多補償嗎？"]
    
    if any(keyword in clean_user_msg for keyword in ['言語辱罵', '精神折磨', '精神暴力']):
        return LOCAL_QA["如果對方沒有動手打我，只是言語辱罵、精神折磨，這樣也能算家暴嗎？"]
    
    if any(keyword in clean_user_msg for keyword in ['保護令地址', '住址保密']):
        return LOCAL_QA["如果申請家暴保護令，他會知道我現在住在哪裡嗎？"]
    
    # 離婚程序相關問題
    if any(keyword in clean_user_msg for keyword in ['離婚步驟', '怎麼離婚', '離婚程序']):
        return LOCAL_QA["想離婚怎麼辦？（離婚的步驟）"]
    
    if any(keyword in clean_user_msg for keyword in ['官司費用', '離婚費用', '律師費']):
        return LOCAL_QA["打一場離婚官司要花多少錢？"]
    
    if any(keyword in clean_user_msg for keyword in ['沒錢請律師', '法律扶助', '免費律師']):
        return LOCAL_QA["如果我沒錢請律師怎麼辦？可以申請「法律扶助」嗎？"]
    
    if any(keyword in clean_user_msg for keyword in ['直接告離婚', '強制調解']):
        return LOCAL_QA["可以直接告離婚嗎？還是一定要先調解？（離婚程序）"]
    
    # 離婚條件相關問題
    if any(keyword in clean_user_msg for keyword in ['什麼情況離婚', '離婚條件', '可以離婚']):
        return LOCAL_QA["在什麼樣的情況下，我可以離婚？"]
    
    if any(keyword in clean_user_msg for keyword in ['分居離婚', '分居多久']):
        return LOCAL_QA["分居可以離婚嗎？分居多久可以離婚？"]
    
    return None

def get_gemini_response(user_message):
    """使用 Gemini API 取得回覆"""
    try:
        # 初始化模型
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        
        # 組合提示詞
        prompt = f"{LAWYER_SYSTEM_PROMPT}\n\n用戶詢問：{user_message}"
        
        # 產生回覆
        response = model.generate_content(prompt)
        return response.text
        
    except Exception as e:
        app.logger.error(f"Gemini API error: {str(e)}")
        return None

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    
    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@line_handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text.strip()
    
    # 問候語處理
    if user_message in ['你好', '您好', '嗨', 'hi', 'Hello', '您好律師']:
        reply_text = """您好！我是婚姻諮詢小幫手!

有什麼法律問題需要協助嗎？例如：
• 離婚程序與條件
• 財產分配問題  
• 子女監護權安排
• 家暴保護與求助
• 扶養費與贍養費

請告訴我您的具體情況，我會提供專業法律分析。"""
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text, quick_reply=QuickReply(items=QUICK_REPLY_ITEMS))
        )
        return
    
    # 非法律相關問題過濾
    if not is_legal_related(user_message):
        reply_text = "我是婚姻諮詢小幫手，如果您有離婚、財產、監護權等相關法律問題，我很樂意為您提供專業分析。"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text, quick_reply=QuickReply(items=QUICK_REPLY_ITEMS))
        )
        return
    
    # 先檢查本地回答
    local_answer = get_local_answer(user_message)
    if local_answer:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=local_answer, quick_reply=QuickReply(items=QUICK_REPLY_ITEMS))
        )
        return
    
    try:
        # 使用 Gemini API
        reply_text = get_gemini_response(user_message)
        
        if not reply_text:
            raise Exception("Gemini API 回傳空值")
            
        # 長度限制處理
        if len(reply_text) > 4000:
            reply_text = reply_text[:4000] + "\n\n※ 因內容較長，建議預約律師進行詳細諮詢。"
            
    except Exception as e:
        app.logger.error(f"Gemini API error: {str(e)}")
        reply_text = """抱歉，目前暫時無法處理您的問題。

緊急聯繫方式：
• 法律扶助基金會：02-2322-5251
• 113保護專線：家庭暴力求助
• 各地方法院訴訟輔導科

請稍後再試或直接聯繫上述單位。"""
    
    # 回覆訊息（帶快速回覆）
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text, quick_reply=QuickReply(items=QUICK_REPLY_ITEMS))
    )

@app.route("/", methods=['GET'])
def home():
    return "婚姻諮商法律小幫手 LINE BOT 運作中！"

if __name__ == "__main__":
    app.run()




