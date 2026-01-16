import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "../"))
import datetime
import re
import requests
import json
import csv
import copy
from urllib.parse import urlparse, parse_qs
from requests_toolbelt import MultipartEncoder


app_id = "xxx"
app_secret = "xxx"

def get_tenant_access_token():
    """
    获取飞书的tenant_access_token
    :return:
    """
    res = requests.post(url='https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal', json={"app_id": app_id, "app_secret": app_secret}).json()
    return res['app_access_token']

def get_headers(access_token):
    return {'Authorization': 'Bearer ' + access_token}

def get_bitable_app_token(token, access_token):
    bitable_info_url = 'https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node'
    bitable_info_res = requests.get(bitable_info_url, headers=get_headers(access_token), params={"token": token, "obj_type": "bitable"}).json()
    if bitable_info_res['code'] !=0:
        raise Exception(f'get_bitable_content_by_token() err bitable_info_res:{json.dumps(bitable_info_res)}')
    return bitable_info_res['data']['node']['obj_token']

def get_vitable_records(bitable_app_token, id, access_token):
    # 获取查询id
    search_id_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{bitable_app_token}/tables/{id}/records/search"
    search_res = requests.post(search_id_url, json={} ,headers=get_headers(access_token)).json()
    if search_res['code'] !=0:
        raise Exception(f'get_vitable_records() err search_res:{json.dumps(search_res)}')
    return [id_info['record_id'] for id_info in search_res['data']['items']]

def get_bitable_content_by_token_id(token, id, access_token):
    bitable_app_token = get_bitable_app_token(token, access_token)
    record_ids = get_vitable_records(bitable_app_token, id, access_token)
    if len(record_ids) ==0:
        return []
    batch_get_url = f'https://open.feishu.cn/open-apis/bitable/v1/apps/{bitable_app_token}/tables/{id}/records/batch_get'
    bitable_info = requests.post(batch_get_url, json={"record_ids": record_ids}, headers=get_headers(access_token)).json()
    if bitable_info['code'] !=0:
        raise Exception(f'get_bitable_content_by_token() err bitable_info:{json.dumps(bitable_info)}')
    
    # 返回所有记录
    return bitable_info['data']['records']
    
def get_sheet_content_by_token_id(token, id, access_token):
    if id is None:
        sheet_info_url = f'https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{token}/sheets/query'
        sheet_info_res = requests.get(sheet_info_url, headers=get_headers(access_token)).json()
        if sheet_info_res['code'] !=0 or len(sheet_info_res['data']['sheets']) == 0:
            raise Exception(f'get_sheet_content_by_token_id() err sheet_info_res:{json.dumps(sheet_info_res)}')
        id = sheet_info_res['data']['sheets'][0]['sheet_id']
        
    open_api_url = f'https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{token}/sheets/{id}'
    sheet_info = requests.get(open_api_url, headers=get_headers(access_token)).json()
    if sheet_info['code'] != 0:
        raise Exception(f'get_sheet_content() get err sheet_info:{json.dumps(sheet_info)}')
    
    sheet = sheet_info['data']['sheet']
    grid_properties = sheet['grid_properties']
    # 列数
    column_count = num_to_col(grid_properties['column_count'])
    
    open_api_url = f'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{token}/values/{id}!A:{column_count}?valueRenderOption=ToString&dateTimeRenderOption=FormattedString'
    
    res = requests.get(open_api_url, headers=get_headers(access_token)).json()
    if res['code'] !=0:
        raise Exception(f'get_sheet_content() get err res:{json.dumps(res)}')
    return res

def get_obj_token(node_token, access_token):
    open_api_url = f'https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node'
    params = {'token': node_token}
    
    # 获取obj_token 与 obj_type
    res = requests.get(open_api_url, headers=get_headers(access_token), params=params).json()
    if res['code'] !=0:
        raise Exception(res['msg'])
    obj_token = res['data']['node']['obj_token']
    obj_type = res['data']['node']['obj_type']
    return obj_token, obj_type
    
def get_wiki_content(url, access_token):
    node_token, id = get_token_and_id(url)
    (obj_token, obj_type) = get_obj_token(node_token, access_token)
    if obj_type not in ["sheet", "bitable"]:
        raise Exception(f"get_wiki_sheet_content get {obj_type} type")
    return get_sheet_content_by_token_id(obj_token, id, access_token) if obj_type == "sheet" else get_bitable_content_by_token_id(obj_token, id, access_token)

def upload_attachment_to_wiki(url, file_path, access_token):
    node_token, id = get_token_and_id(url)
    (obj_token, obj_type) = get_obj_token(node_token, access_token)
    if obj_type not in ["sheet", "bitable"]:
        raise Exception(f"upload_attachment_to_wiki get {obj_type} type")
    # 上传附件
    upload_url = f"https://open.feishu.cn/open-apis/drive/v1/medias/upload_all"
    form = {'file_name': os.path.basename(file_path),
            'parent_type': 'bitable_image',
            'parent_node': obj_token,
            'size': str(os.path.getsize(file_path)),
            'file': (open(file_path, 'rb'))}
    multi_form = MultipartEncoder(form)
    headers= get_headers(access_token)
    headers['Content-Type'] = multi_form.content_type
    response = requests.request("POST", upload_url, headers=headers, data=multi_form).json()
    if response['code'] !=0:
        raise Exception(f"upload_attachment_to_wiki get err response:{json.dumps(response)}")
    return response['data']['file_token']
 
def get_token_and_id(url):
    token = re.search(r'(?:wiki|sheets)/([A-Za-z0-9]+)', url)
    id = re.search(r'sheet|table=(.*)&', url)
    
    token_str = token.group(1) if token else None
    id_str = id.group(1) if id else None
    return (token_str, id_str)   
   
def num_to_col(num):
    string = ""
    while num > 0:
        num, remainder = divmod(num - 1, 26)
        string = chr(65 + remainder) + string
    return string

def write_value_to_csv(value, local_dir):
    fields = {}
    if len(value) > 0:
        for index, key_name in enumerate(value[0]):
            if key_name is None:
                continue
            fields[key_name] = index
        
    value_list = []
    for index, line in enumerate(value):
        if index == 0:
            continue
        value_line = []
        for field_name in fields.keys():
            field_index = fields[field_name]
            value_line.append(line[field_index])
        value_list.append(value_line)
    
    with open(local_dir, 'w', newline='') as f:
        writer = csv.writer(f)
        # 写入字段
        writer.writerow(fields)
        # 写入行数据
        writer.writerows(value_list)
    return local_dir
    
def reply_message(message_id, text, access_token=None):
    if access_token is None:
        access_token = get_tenant_access_token()
    url = 'https://open.feishu.cn/open-apis/im/v1/messages/{}/reply'.format(message_id)
    
    ret_data = {'text': text}
    
    body = {
        "msg_type": "text",
        "content": json.dumps(ret_data, ensure_ascii=False, indent=4),
        'uuid': str(datetime.datetime.now().timestamp())
    }
    res = requests.post(url, headers=get_headers(access_token), json=body).json()
    return res

def send_message(receive_id, text, access_token=None):
    if access_token is None:
        access_token = get_tenant_access_token()
    url = 'https://open.feishu.cn/open-apis/im/v1/messages'
    param = {'receive_id_type': 'chat_id'}
    
    ret_data = {'text':text}
    
    body = {
        'receive_id': receive_id,
        "msg_type": "text",
        "content": json.dumps(ret_data, ensure_ascii=False, indent=4),
        'uuid': str(datetime.datetime.now().timestamp())
    }
    res = requests.post(url, headers=get_headers(access_token), json=body, params=param).json()
    return res

def get_department_member_list(department_id, access_token=None):
    if access_token is None:
        access_token = get_tenant_access_token()
    url = 'https://open.feishu.cn/open-apis/contact/v3/users/find_by_department'
    params = {'department_id': department_id}
    res = requests.get(url, headers=get_headers(access_token), params=params).json()
    if res['code'] !=0:
        raise Exception(f'get_department_member_list() get err res:{json.dumps(res)}')
    return res

def get_chats_member_list(chat_id, access_token=None):
    if access_token is None:
        access_token = get_tenant_access_token()
    url = f'https://open.feishu.cn/open-apis/im/v1/chats/{chat_id}/members/is_in_chat'
    res = requests.get(url, headers=get_headers(access_token)).json()
    if res['code'] !=0 or not res['data']['is_in_chat']:
        return {"data" : {"items": []}}
        # raise Exception(f'get_chats_member_list() get err res:{json.dumps(res)}')
    
    # 获取群成员列表
    url = f'https://open.feishu.cn/open-apis/im/v1/chats/{chat_id}/members'
    res = requests.get(url, headers=get_headers(access_token)).json()
    
    if res['code'] !=0:
        raise Exception(f'get_chats_member_list() get err res:{json.dumps(res)}')
    return res

def get_access_list(url, access_token=None):
    if access_token is None:
        access_token = get_tenant_access_token()
        access_token = get_tenant_access_token()
    parts = re.split('[/?=]', url) 
    type = parts[3]
    if type == 'sheets':
        type = 'sheet'
    
    token, sheet_id = get_token_and_id(url)
    url = f'https://open.feishu.cn/open-apis/drive/v1/permissions/{token}/members'
    params = {'type': type, 'fields': '*'}
    res = requests.get(url, headers=get_headers(access_token), params=params).json()
    if res['code'] !=0:
        raise Exception(f'get_access_list() get err res:{json.dumps(res)}')
    return res

def write_url_to_csv(url, access_token, path):
    if not is_access_url(url, access_token):
        raise Exception(f'write_url_to_csv() have no access!')
    
    # 获取类型，是表格还是知识库
    content_res = get_wiki_content(url, access_token)
    value = content_res['data']['valueRange']['values']
    write_value_to_csv(value, path)
    return path

def get_authorize_url():
    url = f'https://open.feishu.cn/open-apis/authen/v1/authorize'
    params = {
        'app_id': app_id,
        'redirect_uri': 'http://localhost:1758/authorization',
        'scope':'drive:drive docs:doc sheets:spreadsheet wiki:wiki bitable:app docs:permission.member:auth',
        }
    res = requests.get(url, params=params)
    return res.url

def get_user_access_token(authorize_url):
    parsed_url = urlparse(authorize_url)
    parameters = parse_qs(parsed_url.query)
    code = parameters.get('code', [None])[0] 
    
    url = 'https://open.feishu.cn/open-apis/authen/v1/oidc/access_token'
    headers = {'Authorization': 'Bearer ' + get_tenant_access_token(), 'Content-Type': 'application/json; charset=utf-8'}
    body = {
        "grant_type": "authorization_code",
        "code": code
    }
    res = requests.post(url, headers=headers, json=body).json()
    if res['code'] !=0:
        raise Exception(f'get_user_access_token() get err res:{json.dumps(res)}')
    print(res)
    return res['data']['access_token']

def is_access_url(remote_url, access_token):
    node_token, sheet_id = get_token_and_id(remote_url)
    url = f'https://open.feishu.cn/open-apis/drive/v1/permissions/{node_token}/members/auth'
    url_type = re.split('[/?=]', remote_url)[3] 
    params = {'type': 'wiki' if url_type =='wiki' else 'sheet' , 'action': 'view'}
    res = requests.get(url, headers=get_headers(access_token), params=params).json()
    if res['code'] !=0:
        raise Exception(f'is_access_url get err res:{json.dumps(res)}')
    return res['data']['auth_result']

def append_to_feishu_sheet(url: str, rows: list, access_token: str) -> dict:
    node_token, sheet_id = get_token_and_id(url)
    (obj_token, obj_type) = get_obj_token(node_token, access_token)
    values = []
    for row in rows:
        values.append([row])
        
    sheet_content = get_sheet_content_by_token_id(obj_token, sheet_id, access_token)
    headers = sheet_content['data']['valueRange']['values'][0]
    cow = num_to_col(1)
    for index, header in enumerate(headers):
        if header == None:
            cow = num_to_col(index + 1)
            break
        
    # 准备追加数据
    append_data = {
            "valueRange": {
            "range": f"{sheet_id}!{cow}1:{cow}{len(values)}",
            "values": values
        }
    }
    # 执行追加
    headers = {"Authorization": f"Bearer {access_token}"}
    append_url = f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{obj_token}/values_append/"
    
    try:
        response = requests.post(append_url, headers=headers, json=append_data, params={"insertDataOption": "OVERWRITE"})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"API请求失败: {e}")
    
def coverwrite_bitable(url, fields_list, access_token: str):
    node_token, id = get_token_and_id(url)
    (obj_token, obj_type) = get_obj_token(node_token, access_token)
    if obj_type != "bitable":
        raise Exception(f"coverwrite_bitable get {obj_type} type")
    # 覆盖写入
    bitable_app_token = get_bitable_app_token(obj_token, access_token)
    # 1. 先获取查询记录
    record_ids = get_vitable_records(bitable_app_token, id, access_token)
    # 2. 先新增记录
    batch_create_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{bitable_app_token}/tables/{id}/records/batch_create"
    records = []
    for fields in fields_list:
        fields_copy = copy.deepcopy(fields)
        for key, value in fields_copy.items():
            if not isinstance(value, list):
                continue
            if "text" not in value[0]:
                continue
            fields_copy[key] = value[0]["text"]
        records.append({"fields": fields_copy})
        
    create_res = requests.post(batch_create_url, json={"records": records}, headers=get_headers(access_token)).json()
    if create_res['code'] !=0:
        raise Exception(f'coverwrite_bitable() err create_res:{json.dumps(create_res)}')
    # 2.删除查询的记录
    batch_remove_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{bitable_app_token}/tables/{id}/records/batch_delete"
    if len(record_ids) == 0:
        return
    remove_res = requests.post(batch_remove_url, json={"records": record_ids}, headers=get_headers(access_token)).json()
    if remove_res['code'] !=0:
        raise Exception(f'coverwrite_bitable() err remove_res:{json.dumps(remove_res)}')
    return    