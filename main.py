import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
import sqlite3
import os
import requests  
from urllib.parse import urlparse
from file_extensions import FILE_EXTENSIONS 

conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        full_name TEXT NOT NULL,
        department TEXT NOT NULL
    )
''')
conn.commit()

# Функция для создания директорий для пользователя
def create_user_directories(department, full_name):
    base_path = f"storage/{department}/{full_name}"
    directories = [f"{base_path}/images", f"{base_path}/documents", f"{base_path}/other"]

    for directory in directories:
        os.makedirs(directory, exist_ok=True)

    return base_path

# Определяем тип файла по его расширению
def determine_file_type(file_name):
    extension = file_name.split('.')[-1].lower() 

    for file_type, extensions in FILE_EXTENSIONS.items():
        if extension in extensions:
            return file_type
    return 'other'

# Функция для сохранения файла в соответствующую папку
def save_file(file_url, department, full_name):
    parsed_url = urlparse(file_url)
    file_name = os.path.basename(parsed_url.path)
    file_type = determine_file_type(file_name)

    if file_type == 'image':
        save_path = f"storage/{department}/{full_name}/images"
    elif file_type == 'document':
        save_path = f"storage/{department}/{full_name}/documents"
    else:
        save_path = f"storage/{department}/{full_name}/other"

    if not os.path.exists(save_path):
        os.makedirs(save_path)

    local_file_path = f"{save_path}/{file_name}"

    response = requests.get(file_url)
    if response.status_code == 200:
        with open(local_file_path, 'wb') as file:
            file.write(response.content)
        return local_file_path
    else:
        raise Exception(f"Failed to download file from {file_url}")

# Функция для получения информации о пользователе
def get_user_info(user_id):
    cursor.execute('SELECT full_name, department FROM users WHERE user_id=?', (user_id,))
    return cursor.fetchone()

# Функция для добавления информации о пользователе
def add_user_info(user_id, full_name, department):
    cursor.execute('INSERT INTO users (user_id, full_name, department) VALUES (?, ?, ?)', 
                   (user_id, full_name, department))
    conn.commit()
    create_user_directories(department, full_name)

# Авторизация бота в VK
vk_session = vk_api.VkApi(token='token')
vk = vk_session.get_api()
longpoll = VkLongPoll(vk_session)

# Словарь для отслеживания шагов регистрации
registration_steps = {}

# Основной цикл для обработки событий
for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        user_id = event.user_id
        message = event.text.lower()

        user_info = get_user_info(user_id)

        if user_info:
            full_name, department = user_info

            if 'скиньте файл' in message:
                vk.messages.send(user_id=user_id, message="Скиньте файл.", random_id=0)

            elif event.attachments:
                # Получаем данные о сообщении с файлами
                msg_id = event.message_id
                attachments = vk.messages.getById(message_ids=msg_id)['items'][0].get('attachments', [])

                file_url = None

                for attachment in attachments:
                    if attachment['type'] == 'photo':
                        sizes = attachment['photo']['sizes']
                        file_url = sizes[-1]['url'] 
                        break
                    elif attachment['type'] == 'doc':
                        file_url = attachment['doc']['url']
                        break

                if file_url:
                    try:
                        saved_file_path = save_file(file_url, department, full_name)
                        vk.messages.send(user_id=user_id, message=f"Файл сохранен: {saved_file_path}", random_id=0)
                    except Exception as e:
                        vk.messages.send(user_id=user_id, message=f"Ошибка сохранения файла: {str(e)}", random_id=0)
                else:
                    vk.messages.send(user_id=user_id, message="Не удалось определить тип файла.", random_id=0)

        else:
            if user_id not in registration_steps:
                vk.messages.send(user_id=user_id, message="Введите ваше ФИО:", random_id=0)
                registration_steps[user_id] = {"step": "waiting_for_name"}
            
            elif registration_steps[user_id]["step"] == "waiting_for_name":
                full_name = event.text
                registration_steps[user_id]["full_name"] = full_name
                vk.messages.send(user_id=user_id, message="Введите отдел:", random_id=0)
                registration_steps[user_id]["step"] = "waiting_for_department"
            
            elif registration_steps[user_id]["step"] == "waiting_for_department":
                department = event.text
                full_name = registration_steps[user_id]["full_name"]
                add_user_info(user_id, full_name, department)
                vk.messages.send(user_id=user_id, message="Вы успешно зарегистрированы!", random_id=0)
                del registration_steps[user_id]
