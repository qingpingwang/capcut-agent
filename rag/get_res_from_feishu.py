import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from rag.feishu_doc_utils import get_tenant_access_token, get_wiki_content

# 获取当前文件地址
data_path = Path(__file__).parent / "data"
data_path.mkdir(parents=True, exist_ok=True)

res_info = {
    "文字动画": "",
    "画面动画": "",
    "贴片": "",
    "特效": "",
    "转场": "",
    "滤镜": "",
    "音效": ""
}

def process_one_res(res_name, res_url):
    access_token = get_tenant_access_token()
    result = {}
    for row in get_wiki_content(res_url, access_token):
        name = row['fields']["名称"][0]["text"]
        # 取链接or封面图地址
        if "链接" in row['fields']:
            url = row['fields']["链接"]["link"]
        else:
            url = row['fields']["封面图地址"]["link"]
        content_str = ""
        for field_item in row['fields']["内容"]:
            if field_item['type'] == "text":
                content_str += field_item['text']
            elif field_item['type'] == "link":
                content_str += field_item['link']
            elif field_item['type'] == "url":
                content_str += field_item['link']
        result[name] = {
            "desc": row['fields']["描述"][0]["text"],
            "content": content_str,
            "url": url
        }
    # 写入到文件，覆盖写入
    with open(data_path / f"{res_name}.json", "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
    return result
        
def main():
    for res_name, res_url in res_info.items():
        process_one_res(res_name, res_url)
        
        
def get_jianying_res_info():
    # 从本地文件加载，文件名做key，value为文件内容
    result = {}
    for file in data_path.glob("*.json"):
        with open(file, "r") as f:
            result[file.stem] = json.load(f)
    return result

if __name__ == "__main__":
    main()