import telebot
from telebot import types
from telebot.util import smart_split
from multiprocessing import Process
import sqlite3 as sql
import requests
from bs4 import BeautifulSoup as bs, Tag
import re
import io
from urllib.parse import unquote
from string import ascii_lowercase
import threading
from time import sleep
import schedule
import numpy as np


# replace <your_bot_token> with token that tg bot @BotFather sent you
config = {
    'token': '<your_bot_token>'
}


# class for work with database where every bot user has one own subscriptions table
class UserDb(object):
    def __init__(self, user_id):
        self.__conn = sql.connect('users.db')
        self.__cursor = self.__conn.cursor()
        self.__id = user_id
        self.__cursor.execute(
            """CREATE TABLE IF NOT EXISTS """ + f"""U{self.__id}""" + """(
                id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, 
                post_id INTEGER);"""
        )
        self.__conn.commit()

    # returns id of the latest post of chosen group
    def select_groups_post(self, group_id):
        try:
            self.__cursor.execute(f"""SELECT * from U{self.__id} where id = ?""", (group_id,))
            return int(self.__cursor.fetchone()[1])
        except TypeError:
            return -2

    # pretty much the same to select_groups_post func but it returns ids of posts of all groups
    def select_all_groups_posts(self):
        try:
            self.__cursor.execute(f"""SELECT * from U{self.__id}""")
            return [i[1] for i in self.__cursor.fetchall()]
        except TypeError:
            return [-2]

    # returns ids of all groups
    def select_all_groups(self):
        try:
            self.__cursor.execute(f"""SELECT * from U{self.__id}""")
            return [i[0] for i in self.__cursor.fetchall()]
        except TypeError:
            return []

    # adds a group and its latest publication to user's table
    def insert_group(self, lst_data):
        self.__cursor.execute(f"""INSERT or IGNORE INTO U{self.__id} (id, post_id) VALUES (?, ?)""", lst_data)
        self.__conn.commit()

    # exact opposite of insert_group
    def delete_group(self, group_id):
        self.__cursor.execute(f"""DELETE FROM U{self.__id} where id = ?""", (group_id,))
        self.__conn.commit()

    # lists ids of all bot users
    def get_users(self):
        self.__cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        return [int(v[0][1:]) for v in self.__cursor.fetchall() if v[0] != "sqlite_sequence" and v[0] != "U0"]

    # removes user from database and clears all user's subscriptions
    def delete_user(self):
        self.__cursor.execute(f"""DROP TABLE U{self.__id}""")
        self.__conn.commit()
        self.__conn.close()


possible_links = (
    'https://vk.com/',
    'https://m.vk.com/'
)


# class that is the same to UserAgent from fake-useragent module, but it doesn't cause any errors on start
class UserAgent(object):
    @staticmethod
    def random():
        user_agent_list = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 '
            'Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:77.0) Gecko/20100101 Firefox/77.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/83.0.4103.97 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:77.0) Gecko/20100101 Firefox/77.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 '
            'Safari/537.36',
            'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.8.1.19) Gecko/20081216 Ubuntu/8.04 (hardy) Firefox/2.0.0.19',
            'Mozilla/5.0 (X11; U; Linux i586; en-US; rv:1.7.3) Gecko/20050924 Epiphany/1.4.4 (Ubuntu)',
            'Mozilla/5.0 (Macintosh; U; PPC Mac OS X; en-US) AppleWebKit/125.4 (KHTML, like Gecko, Safari) '
            'OmniWeb/v563.15',
            'Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.0; en) Opera 8.0',
            'Mozilla/5.0 (X11; U; FreeBSD; i386; en-US; rv:1.7) Gecko',
            'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.0.1) Gecko/2008070208 Firefox/3.0.1',
            'Mozilla/5.0 (X11; U; Linux; i686; en-US; rv:1.6) Gecko Debian/1.6-7'
        ]
        return user_agent_list[np.random.randint(0, 12, dtype='int8')]


# a big class object of which provides a possibility of comfortable work with wall of parsed vk community page
class Post(object):
    def __init__(self, wall, post_view_hash, user_id_value):
        self.__post_view_hash = post_view_hash
        self.__user_id = user_id_value
        self.__db = UserDb(self.__user_id)
        try:
            self.__main_block = wall.find_all(
                'div',
                post_view_hash=self.__post_view_hash
            )[0]

        except IndexError:
            self.__main_block = ''
        if isinstance(self.__main_block, Tag):
            self.__post_author = self.__main_block.find(
                'a',
                class_="author"
            ).text
        else:
            self.__post_author = 'unknown'
        self.find_id()

    # here we send any content of vk publication (images, text, author name, events, etc.)
    def post_content(self):
        if isinstance(self.__main_block, Tag):
            if self.__post_author is not None and \
            (isinstance(self.__post_author, Tag) or isinstance(self.__post_author, str)):
                client.send_message(
                    self.__user_id,
                    self.__post_author
                )
            try:
                self.__photos_block = self.__main_block.find(
                    'div',
                    class_='page_post_sized_thumbs clear_fix'
                )
            except IndexError:
                self.__photos_block = ''

            videos_links = []
            if isinstance(self.__photos_block, Tag):
                post_photos_blocks = self.__photos_block.find_all('a')
                photos_links = []
                for post_photos_block in post_photos_blocks:
                    links_type, link = self.get_post_photos_link(post_photos_block)
                    if links_type == 'photo_link':
                        photos_links.append(link)
                    elif links_type == 'video_link':
                        videos_links.append(link)

                if None in photos_links:
                    for (i, photos_link) in list(enumerate(photos_links)):
                        if photos_link is None:
                            photos_links[i] = (i, '')
                    photos_links = [i_link[1] for i_link in photos_links]
                photos_links = set(photos_links)
                if '' in photos_links:
                    photos_links.remove('')
                photos_links = list(photos_links)
                if len(photos_links) > 1:
                    for photos_link in photos_links:
                        self.send_post_photo(photos_link)
                elif len(photos_links) == 1:
                    self.send_post_photo(photos_links[0])
                if len(videos_links) > 0:
                    for videos_link in videos_links:
                        if videos_link is not None and len(videos_link) > 0:
                            try:
                                self.send_post_video(videos_link)
                            except:
                                continue
            media_blocks = self.__main_block.find_all(
                'a',
                class_="media_link__title"
            )
            media_links = ''
            if media_blocks is not None and media_blocks != []:
                for media_block in media_blocks:
                    media_links += '\n' + self.get_post_links(media_block, flag='media')['links'][0]

            event_block = self.__main_block.find_all(
                'a',
                class_="page_media_event_content"
            )
            event_links = ''
            if event_block is not None and event_block != []:
                event_links += ' ' + \
                               '\n'.join([f'{possible_links[0][:-1]}{str(el.get("href"))}' for el in event_block])
            post_text_blocks = self.__main_block.find_all('div', class_="wall_post_text")

            check_text = [post_text_block for post_text_block in post_text_blocks
                          if post_text_block.text is not None and len(post_text_block.text) > 0]
            if check_text is not None and len(check_text) > 0:
                for post_text_block in post_text_blocks:
                    post_links = self.get_post_links(post_text_block)
                    final_post_text = self.get_post_text(post_text_block, post_links)
                    if len(final_post_text) + len('\n'.join(videos_links)) > 2047:
                        final_post_text = smart_split(final_post_text, 2048)
                        for small_text in final_post_text:
                            if post_text_blocks.index(post_text_block) + 1 == len(post_text_blocks) and \
                                    final_post_text.index(small_text) + 1 == len(final_post_text):
                                small_text += '\n' + '\n'.join(videos_links) + media_links + event_links
                            if len(small_text) > 0:
                                client.send_message(
                                    self.__user_id,
                                    small_text
                                )
                    else:
                        if post_text_blocks.index(post_text_block) + 1 == len(post_text_blocks):
                            final_post_text += '\n' + '\n'.join(videos_links) + media_links + event_links
                            if len(final_post_text) > 0:
                                client.send_message(
                                    self.__user_id,
                                    final_post_text
                                )
            else:
                final_post_text = ''
                if len(videos_links) > 0:
                    final_post_text += '\n'.join(videos_links)
                final_post_text += media_links + event_links
                if len(final_post_text) > 0:
                    client.send_message(
                        self.__user_id,
                        final_post_text
                    )
            self.__db.delete_group(self.__group_id)
            self.__db.insert_group([self.__group_id, self.__id])

    # this function gets the id of the latest vk post. if a content of the latest post hadn't been sent before,
    # function sends it now
    def find_id(self):
        if isinstance(self.__main_block, Tag):
            full_id = self.__main_block.get('data-post-id')
            full_id = full_id.split('_')
            self.__id = int(full_id[1])
            self.__group_id = int(full_id[0][1:])
        else:
            self.__id = -1
            self.__group_id = -1

        saved_post_id = self.__db.select_groups_post(self.__group_id)
        if (self.__id != - 1) and (saved_post_id == -2 or (saved_post_id != -2 and self.__id > saved_post_id)):
            self.post_content()

    # returns a name of post's author
    @property
    def post_author(self):
        if self.__post_author is not None and len(str(self.__post_author)) > 0:
            return self.__post_author
        else:
            return '\"unknown\"'

    # returns the id of a community from which post was grabbed
    @property
    def group_id(self):
        return self.__group_id

    # analyzes post text and returns dictionary with links and #hashtags
    def get_post_links(self, post_text_block, flag=''):
        try:
            links, hashtags = [], []
            if flag == 'media':
                post_links = [post_text_block.get('href')]
            else:
                post_links = [i.get('href') for i in post_text_block.find_all('a')]
            post_links = [str(unquote(unquote(i))) for i in post_links if i is not None]
            for i in post_links:
                if i[:13] == '/away.php?to=':
                    links.append(i[13:])
                elif i[:23] == '/feed?section=search&q=':
                    hashtags.append(i[23:])
            links = list(enumerate(links))
            for (index, link) in links:
                end = 0
                for m in re.finditer('&post=', link):
                    end = m.start()
                    break
                if end != 0:
                    good_link = link[:end]
                    links[index] = (index, good_link)
            if len(links) != 0:
                links = [i_link[1] for i_link in links]
            return {'links': links,
                    'hashtags': hashtags}
        except:
            return {'links': [],
                    'hashtags': []}

    # returns a pretty version of vk post text
    def get_post_text(self, post_text_block, post_links):
        post_text = list(enumerate(list(post_text_block.text)))
        text = ''
        for b in post_text:
            i = b[1]
            text += i
            if post_text.index(b) + 2 < len(post_text):
                if post_text[post_text.index(b) + 1][1] != ' ' and \
                        post_text[post_text.index(b) + 1][
                            1] not in f'{ascii_lowercase}' and \
                        post_text[post_text.index(b) + 1][1] not in (';', '!', '?', ',', '.', ':') and \
                        post_text[post_text.index(b) + 2][1] not in (';', '!', '?', ',', '.', ':') and \
                        ((i in (';', '!', '?', ','))
                         or (i in (':', '.') and
                             f'{post_text[post_text.index(b) + 1][1]}{post_text[post_text.index(b) + 2][1]}' != '//'
                             and not 48 <= ord(post_text[post_text.index(b) + 1][1]) <= 57)):
                    text += ' \n'
        post_text = list(enumerate(list(text.split(' '))))
        counter = 0
        if len(post_links['links']) > 0:
            for i in post_text:
                if len(i[1]) >= 9:
                    starts = []
                    for p in ('ftp://', 'http://', 'https://'):
                        if p in i[1]:
                            for m in re.finditer(p, i[1]):
                                starts.append(m.start())
                    if len(starts) == 0:
                        continue
                    start = np.min(np.array(starts))
                    iter_links = i[1][start:]
                    for p in ('ftp://', 'http://', 'https://'):
                        if p in i[1]:
                            iter_links = iter_links.split(p)
                            temp_iter_links = []
                            for iter_link in iter_links:
                                if '/away.php?to=' not in iter_link and 'redirect' not in iter_link:
                                    temp_iter_links.append(iter_link)
                            if '' in temp_iter_links:
                                ttils = []
                                for til in temp_iter_links:
                                    if til != '':
                                        ttils.append(til)
                                temp_iter_links = ttils
                            iter_links = ' '.join(temp_iter_links)
                    iter_links = len(iter_links.split(' '))
                    if counter < len(post_links['links']):
                        if iter_links == 1:
                            iter_links = ' ' + post_links['links'][counter] + ' '
                            counter += 1
                        else:
                            iter_links = '\n' + ',\n'.join(post_links['links'][counter:counter + iter_links]) + ',\n'
                            counter += len(iter_links)
                    else:
                        iter_links = ''
                    if start > 0:
                        small_link = i[1][:start]
                    else:
                        small_link = ''
                    small_link += iter_links
                    post_text[i[0]] = (i[0], small_link)

        if len(post_links['hashtags']) > 0:
            post_text.reverse()
            temp_text = []
            for (index, i) in post_text:
                if len(i) > 0:
                    if i[0] != '#':
                        temp_text.append((index, i))
                    else:
                        temp_text.append((index, i[1:]))
            post_text, temp_text = temp_text, []
            post_text.reverse()
            for (index, i) in post_text:
                if len(i) > 0:
                    if i[0] != '#':
                        temp_text.append((index, i))
                    else:
                        temp_text.append((index, i[1:]))
            post_text = temp_text
            if len(post_links['hashtags']) != 0:
                hashtags = ' '.join(post_links['hashtags']) + '\n'
            else:
                hashtags = ''
            post_text = hashtags + ' '.join((i[1] for i in post_text))
        else:
            post_text = ' '.join((i[1] for i in post_text))
        post_text = post_text.replace('See more', '')
        post_text = post_text.replace('In zijn geheel tonen... \n', '')
        return post_text

    # finds links of post's photos
    def get_post_photos_link(self, post_photos_block):
        post_photos_link = str(post_photos_block.get('style'))
        post_videos_link = f'{possible_links[0][:-1]}{str(post_photos_block.get("href"))}'
        if len(post_photos_link) > 0 and 'https://sun' in post_photos_link and 'type=album' in post_photos_link:
            start_link = end_link = 0
            for m in re.finditer('https://sun', post_photos_link):
                start_link = m.start()
                break
            for m in re.finditer('type=album', post_photos_link):
                end_link = m.end()
                break
            post_photos_link = post_photos_link[start_link:end_link]
            post_photos_link = post_photos_link.replace('amp;', '')
            return 'photo_link', post_photos_link
        if len(post_videos_link) > 14:
            video_page, tries, soup = None, 0, None
            while video_page is None and tries < 2:
                header = {'user-agent': UserAgent().random()}
                video_page = requests.get(post_videos_link, headers=header).text
                soup = bs(video_page, 'lxml')
                if soup is None:
                    tries += 1
                else:
                    break
            if soup is not None:
                videos_link = soup.find('link', itemprop="embedUrl")
                if videos_link is not None:
                    video_link = str(videos_link.get('href'))
                    return 'video_link', video_link

    # sends post's photos to user. we use python io to do it "cleaner"
    def send_post_photo(self, photos_link):
        url = f"https://api.telegram.org/bot{config['token']}/sendPhoto"
        header = {'user-agent': UserAgent().random()}
        remote_image = requests.get(photos_link, headers=header)
        photo = io.BytesIO(remote_image.content)
        photo.name = 'img.jpg'
        files = {'photo': photo}
        data = {'chat_id': str(self.__user_id)}
        header = {'user-agent': UserAgent().random()}
        r = requests.post(url, headers=header, files=files, data=data)

    # turns any link of vk player into the link that connects bot to vk server.
    # bot downloads video from server and sends it to user
    def send_post_video(self, videos_link):
        if 'https://vk.com/video_ext.php?oid=' not in videos_link:
            return None
        soup, tries, header = None, 0, ''
        while soup is None and tries < 3:
            header = {'user-agent': UserAgent().random()}
            response = requests.get(videos_link, headers=header).text
            soup = bs(response, 'lxml')
            if soup is None:
                tries += 1
                sleep(1)
        if soup is not None:
            block, tmp_block, tmp_start, tmp_end = str(soup), str(soup), 0, 0
            for m in re.finditer('","duration":', tmp_block):
                tmp_start = m.end()
                break
            tmp_block = tmp_block[tmp_start:]
            for m in re.finditer(',"t"', tmp_block):
                tmp_end = m.start()
            tmp_block = tmp_block[:tmp_end]
            duration = 0
            if tmp_block != '':
                duration = int(tmp_block)
            if duration > 180 or duration == 0:
                return None
            for quality in ((480, 720), (360, 480), (240, 360)):
                start, end = 0, 0
                url = f"https://api.telegram.org/bot{config['token']}/sendVideo"
                for m in re.finditer('\"url{}\":\"'.format(quality[0]), block):
                    start = m.end()
                    break
                for m in re.finditer('\",\"url{}\":\"'.format(quality[1]), block):
                    end = m.start()
                    break
                if (not start or not end) and quality[0] == 240:
                    for m in re.finditer('\"><BaseURL>', block):
                        start = m.end()
                        break
                    for m in re.finditer('<\\\/BaseURL>'.format(quality[1]), block):
                        end = m.start()
                        break
                    if not start and not end:
                        return None
                elif (not start or not end) and quality[0] > 240:
                    continue
                link = block[start:end]
                link = link.replace('\\/', '/')
                link = link.replace('amp;', '')
                remote_video = requests.get(link, headers=header)
                video = io.BytesIO(remote_video.content)
                video.name = 'vid.mp4'
                files = {'video': video}
                data = {'chat_id': str(self.__user_id)}
                header = {'user-agent': UserAgent().random()}
                r = requests.post(url, headers=header, files=files, data=data)
                break


# the easiest way to get div tag that contains vk post is to find div with class_ == <post_view_hash>.
# here we parse a page of vk group to get this universal hash. remember that post_view_hash changes
# from time to time
def get_post_view_hash():
    global global_post_view_hash
    wall, tries = None, 0
    while wall is None and tries < 10:
        header = {'user-agent': UserAgent().random()}
        response = requests.get(f'{possible_links[0]}{"vkstickers"}', headers=header).text
        soup = bs(response, 'lxml')
        wall = soup.find('div', id="page_wall_posts")
        if wall is None:
            tries += 1
            sleep(1)
    if wall is not None:
        block = wall.find_all(
            'div',
            class_="_post post page_block all own post--with-likes closed_comments deep_active"
        )[0]
        global_post_view_hash = str(block.get("post_view_hash"))
    else:
        global_post_view_hash = ''
    print(global_post_view_hash)
    return global_post_view_hash


get_post_view_hash()


# getting a web page vk.com/group_example for a future parsing
def get_wall(group_link, user_id):
    wall, tries = None, 0
    while wall is None and tries < 3:
        header = {'user-agent': UserAgent().random()}
        response = requests.get(group_link, headers=header).text
        soup = bs(response, 'lxml')
        wall = soup.find('div', id="page_wall_posts")
        if wall is None:
            tries += 1
            sleep(1)
        else:
            break
    if wall is not None:
        return wall
    else:
        client.send_message(
            user_id,
            f'Не удаётся получить публикации {group_link}. '
            f'Если Вы уверены, что ссылка рабочая, а сообщество открытое, '
            f'попробуйте позже.'
        )
        return 'empty_wall'


# universal function for updating chosen community's posts
def update_group_posts(group_link, user_id_value):
    wall = get_wall(group_link, user_id_value)
    if wall != 'empty_wall':
        Post(wall, global_post_view_hash, user_id_value)


# creating bot object
client = telebot.TeleBot(config['token'])


# handler of start message
@client.message_handler(commands=['start'])
def start_message(message):
    client.send_message(
        message.chat.id,
        'Приветствую. Я помогу Вам перенести ленту подписок Вконтакте в этот чат.\n'
        'Для добавления сообщества vk в локальные подписки отправьте /subscribe.'
    )


# sends a message that contains all your local subscriptions to vk communities
@client.message_handler(commands=['groups'])
def get_groups(message):
    groups = UserDb(message.chat.id).select_all_groups()
    if len(groups) > 0:
        groups = [f'{possible_links[0]}public{i}' for i in groups]
        reply = 'Ваши подписки:\n' + "\n".join(tuple(groups))
    else:
        reply = 'Вы ещё не подписаны ни на одно сообщество. Отправьте /subscribe, чтобы подписаться.'
    client.send_message(
        message.chat.id,
        reply
    )


# asks which communities bot should check for new posts
@client.message_handler(commands=['posts'])
def get_posts(message):
    groups = UserDb(message.chat.id).select_all_groups()
    if len(groups) == 0:
        client.send_message(
            message.chat.id,
            'Вы ешё не подписаны ни на одно сообщество. Отправьте /subscribe для первой подписки'
        )
    else:
        markup_inline = types.InlineKeyboardMarkup()
        item_all = types.InlineKeyboardButton(text='Все', callback_data='all')
        item_special = types.InlineKeyboardButton(text='Выбрать', callback_data='special')
        markup_inline.add(item_all, item_special)

        client.send_message(
            message.chat.id,
            'Какие сообщества проверить на наличие новых публикаций?',
            reply_markup=markup_inline
        )


# asks if user want to remove all his/her data from database
@client.message_handler(commands=['exit'])
def full_exit(message):
    markup_inline = types.InlineKeyboardMarkup()
    item_all = types.InlineKeyboardButton(text='Да', callback_data='full_exit')
    item_special = types.InlineKeyboardButton(text='Нет', callback_data='do_not_exit')
    markup_inline.add(item_all, item_special)

    client.send_message(
        message.chat.id,
        'Вы уверены, что хотите выйти? Список подписок будет удалён с сервера, '
        'но у Вас все ещё останется доступ ко всем сообщениям этого чата',
        reply_markup=markup_inline
    )


# call backs
@client.callback_query_handler(func=lambda call: True)
def answer(call):
    groups = UserDb(call.message.chat.id).select_all_groups()
    if call.data == 'all':
        if len(groups) > 1:
            for group in groups:
                update_group_posts(f'{possible_links[0]}public{group}', call.message.chat.id)
        else:
            update_group_posts(f'{possible_links[0]}public{list(groups)[0]}', call.message.chat.id)

    elif call.data == 'special':
        if len(groups) > 1:
            get_groups(call.message)
            msg = client.send_message(
                call.message.chat.id,
                'Отправьте ссылку на нужное сообщество '
                'или его краткое имя из выпавшего списка.'
            )
            client.register_next_step_handler(msg, choose_group)
        else:
            update_group_posts(f'{possible_links[0]}public{list(groups)[0]}', call.message.chat.id)

    elif call.data == 'add_more':
        subscribe(call.message)
    elif call.data == 'remove_more':
        unsubscribe(call.message)
    elif call.data == 'full_exit':
        UserDb(call.message.chat.id).delete_user()
        client.send_message(
            call.message.chat.id,
            'Ваши данные удалены успешно.'
        )
    elif call.data == 'do_not_exit':
        client.send_message(
            call.message.chat.id,
            'Ваши данные не изменены.'
        )
        get_groups(call.message)


# runs add_group function until user's reply is a valid vk group link
@client.message_handler(commands=['subscribe'])
def subscribe(message):
    msg = client.send_message(
        message.chat.id,
        'Отправьте ссылку на сообщество VK, '
        'публикации которого Вы хотите просматривать.\n'
        'Формат:\nhttps://vk.com/group_name_example\nили'
        '\nhttps://vk.com/public1234567890'
    )
    while True:
        try:
            client.register_next_step_handler(msg, group_handler, 'add')
            break
        except ValueError:
            continue


# runs add_group function until user's reply is a valid vk community's link
@client.message_handler(commands=['unsubscribe'])
def unsubscribe(message):
    get_groups(message)
    msg = client.send_message(
        message.chat.id,
        'Отправьте ссылку на сообщество VK, '
        'от которого Вы хотите отписаться.\n'
        'Формат:\nhttps://vk.com/group_name_example\nили'
        '\nhttps://vk.com/public1234567890'
    )
    while True:
        try:
            client.register_next_step_handler(msg, group_handler, 'remove')
            break
        except ValueError:
            continue


# returns a string with chosen group
def choose_group(message):
    msg = message.text.lower()
    groups = UserDb(message.chat.id).select_all_groups()
    if msg in groups:
        chosen_group = f'{possible_links[0]}public{msg}'
        wall = get_wall(chosen_group, message.chat.id)
        if wall != 'empty_wall':
            Post(wall, global_post_view_hash, message.chat.id)
    elif (msg[: 15] == possible_links[0]) or \
            (msg[: 17] == possible_links[1]):
        chosen_group = msg
        wall = get_wall(chosen_group, message.chat.id)
        if wall != 'empty_wall':
            Post(wall, global_post_view_hash, message.chat.id)
    else:
        client.register_next_step_handler(msg, choose_group)


# adds/removes group from your local vk subscriptions
def group_handler(message, flag=''):
    msg = message.text.lower()
    reply = 'Ссылка введена неправильно. Попробуйте ещё раз.'
    user_db = UserDb(message.chat.id)
    groups = user_db.select_all_groups()
    for possible_link in possible_links:
        if msg[:len(possible_link)] == possible_link:

            wall = get_wall(msg, message.chat.id)
            if wall != 'empty_wall':
                post = Post(wall, global_post_view_hash, message.chat.id)

                group = post.group_id
                if flag == 'add':
                    if int(group) in groups:
                        reply = f'Вы уже подписаны на {post.post_author}'
                    else:
                        reply = f'Сообщество {post.post_author} добавлено успешно.'
                elif flag == 'remove':
                    user_db.delete_group(group)
                    reply = f'Вы успешно отписались от {group}'
                break

    if reply != 'Ссылка введена неправильно. Попробуйте ещё раз.':
        markup_inline = types.InlineKeyboardMarkup()
        if flag == 'add':
            text, callback_data = 'Добавить ещё', 'add_more'
        elif flag == 'remove':
            text, callback_data = 'Отписаться ещё', 'remove_more'
        else:
            text, callback_data = '', ''
        markup_inline.add(types.InlineKeyboardButton(text=text, callback_data=callback_data))
        client.send_message(
            message.chat.id,
            reply,
            reply_markup=markup_inline
        )
    else:
        client.register_next_step_handler(message, group_handler, flag)


# updates walls of all bot users. every wall updater is multiprocessing.process
def update_users_walls():
    user_ids = UserDb(0).get_users()
    processes = []
    if len(user_ids):
        for user_id in user_ids:
            process = Process(target=update_wall, args=(user_id,))
            processes.append(process)
            process.start()
        for process in processes:
            process.join()


# user's wall updater
def update_wall(user_id):
    groups = UserDb(user_id).select_all_groups()
    errors = 0
    if len(groups):
        for group in groups:
            try:
                update_group_posts(f'{possible_links[0]}public{group}', user_id)
            except:
                errors += 1
            if errors == len(groups):
                UserDb(user_id).delete_user()


# checks every 10 seconds if any scheduled action must be done
def schedule_checker():
    while True:
        schedule.run_pending()
        sleep(10)


# adds a thread that updates walls of all users
def run_update_users_walls():
    thread = threading.Thread(target=update_users_walls)
    thread.start()
    thread.join()


# updates global post view hash in its own thread
def run_get_post_view_hash():
    thread = threading.Thread(target=get_post_view_hash)
    thread.start()
    thread.join()


run_update_users_walls()
schedule.every(15).minutes.do(run_get_post_view_hash)
schedule.every(7).minutes.do(run_update_users_walls)

# adds schedule checker to a special thread
threading.Thread(target=schedule_checker).start()

# bot polling
client.polling(none_stop=True, interval=0)
