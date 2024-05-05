#!/usr/bin/env python
# -*- coding: utf-8 -*-

# parse.py - converts telegram json to Obsidian md.
# Copyright (c) 2020, Lev Brekalov
# Changes from progxaker, 2021

# TODO summary:
# - replies
# - single/muliple tags
# - forwarded posts
# - custom post header

import os
import argparse
import json
import logging
import re
from datetime import datetime

log = logging.getLogger(__name__)

def parse_tags(text_entities):

    tags = []
    for obj in text_entities:
        if obj['type'] == 'hashtag':
            tags.append(obj['text'])

    return ' '.join(tags)

def print_default_post_header(post, user_id):

    '''
    returns default post header
    '''

    post_title = post['id']
    post_date = datetime.fromisoformat(post['date'])
    post_tags = parse_tags(post['text_entities'])

    # TODO: support for custom header
    post_header = '---\n'\
        'title: {title}\n'\
        'date: {date}\n'.format(title=post_title, date=post_date)

    if post_tags:
        post_header += 'tags: {tags}\n'.format(tags=post_tags)

    if 'from_id' in post:
        if post['from_id'] != 'user{}'.format(user_id):
            post_header += "from: '{name}' ({user_id})\n".format(name=post['from'], user_id=post['from_id'])

    if 'forwarded_from' in post:
        post_header += "forwarded\_from: '{}'\n".format(post['forwarded_from'])

    if 'saved_from' in post:
        post_header += "saved\_from: '{}'\n".format(post['saved_from'])

    post_header += 'layout: post\n'\
                   '---\n'

    return post_header


def print_custom_post_header(post_header_file, *args):

    '''
    now unusable (i dunno how it may work)
    '''

    with post_header_file as f:
        post_header_content = read(post_header_file)
    for arg in args:
        pass
    return post_header_content


def parse_post_photo(post, photo_dir):

    '''
    converts photo tag to markdown image link
    '''

    post_photo = '![image]({src})\n\n'.format(src=post['photo'])

    return post_photo


def text_format(string, fmt):

    '''
    wraps string in markdown-styled formatting
    '''

    if fmt in ('*', '**', '***', '`', '```'):
        output = '{fmt}{txt}{fmt}'
    elif fmt == '```':
        output = '{fmt}\n{txt}\n{fmt}'
    else:
        output = '<{fmt}>{txt}</{fmt}>'

    output = output.format(fmt=fmt, txt=string.strip())
    output += '\n' * string.split('\n').count('') * string.endswith('\n')
    return output


# Deserialization based on tdesktop source code
# https://github.com/telegramdesktop/tdesktop/blob/7e071c770f7691ffdbbbd38ac3e17c9aae4d21b3/Telegram/SourceFiles/export/output/export_output_json.cpp#L26-L70
#
# TODO: Implement the last two 'if else' statements.
def deserialize_string(text):

    text.replace(r'\n', '\n')
    text.replace(r'\r', '\r')
    text.replace(r'\t', '\t')
    text.replace(r'\"', '"')
    text.replace(r'\\', '\\')

    return text

# TODO: Put the inline image to the end of the Markdown file.
def text_link_format(text, link):

    '''
    formats links
    '''

    # FIXME: Process text such as [.\n](link)
    if text == u'\u200b' or text == u'\u200b\u200b' or text == '\xa0':
        log.debug('The text is zero-width space, process as an inline image.')
        link_fmt = '> ![]({href})\n\n'.format(href=link)
    else:
        # convert telegram links to anchors
        # this implies that telegram links are pointing to the same channel
        if link.startswith('https://t.me/c/'):
            link = '#' + link.split('/')[-1]
        link_fmt = '[{text}]({href})'
        link_fmt = link_fmt.format(text=text, href=link)
        link_fmt += '\n' * text.count('\n') * text.endswith('\n')

    return link_fmt


def parse_text_object(obj):

    '''
    detects type of text object and wraps it in corresponding formatting
    '''

    obj_type = obj['type']
    obj_text = deserialize_string(obj['text'])

    log.debug("Process the '%s' object of the post #%i with the content %r.", obj_type, post_id, obj)

    if obj_type == 'text_link':
        return text_link_format(obj_text, obj['href'])

    elif obj_type == 'link' or obj_type == 'email':
        link = obj_text.strip()
        link = 'https://' * (obj_type == 'link') * \
            (1 - link.startswith('https://')) + link
        post_link = '<{href}>'.format(href=link)
        return post_link

    elif obj_type == 'phone':
        return obj_text

    elif obj_type == 'italic':
        return text_format(obj_text, '*')

    elif obj_type == 'bold':
        return text_format(obj_text, '**')

    elif obj_type == 'code':
        return text_format(obj_text, '`')

    elif obj_type == 'pre':
        return text_format(obj_text, '```')

    elif obj_type == 'underline':
        return text_format(obj_text, 'u')

    elif obj_type == 'strikethrough':
        return text_format(obj_text, 's')


def parse_post_text(post):
    # TODO: handle reply-to
    post_raw_text = post['text']
    post_parsed_text = ''

    if type(post_raw_text) == str:
        return str(post_raw_text)

    else:
        for obj in post_raw_text:
            if type(obj) == str:
                post_parsed_text += obj
            else:
                post_parsed_text += str(parse_text_object(obj))

        return post_parsed_text

def parse_post_media(post, media_dir):

    '''
    wraps file links to Obsidian link
    '''

    post_media = '![[{src}]]\n\n'.format(src=post['file'])

    return post_media


def parse_post(post, photo_dir, media_dir):

    '''
    converts post object to formatted text
    '''

    post_output = ''

    # optional image
    if 'photo' in post:
        post_output += str(parse_post_photo(post, photo_dir))

    # optional media
    if 'media_type' in post:
        post_output += str(parse_post_media(post, media_dir))

    # post text
    post_output += str(parse_post_text(post, stickers_dir))

    return post_output


def main():

    parser = argparse.ArgumentParser(
            usage='%(prog)s [options] json_file',
            description='Convert exported Telegram channel data json to \
                    bunch of markdown posts ready to use with Obsidian')
    parser.add_argument(
            'json', metavar='json_file',
            help='result.json file from telegram export')
    parser.add_argument(
            '--out-dir', metavar='out_dir',
            nargs='?', default='formatted_posts',
            help='output directory for markdown files\
                    (default: formatted_posts)')
    parser.add_argument(
            '--log-level', metavar='log_level',
            nargs='?', default='warn',
            help='Set the logging level (e.g., debug, info, warning,\
                    error, critical)')
    args_wip = parser.add_argument_group('work in progress')
    args_wip.add_argument(
            '--post-header', metavar='post_header',
            nargs='?',
            help='yaml front matter for your posts \
                    (now doesn\'t work)')
    args_wip.add_argument(
            '--photo-dir', metavar='photo_dir',
            nargs='?', default='photos',
            help='location of image files. this changes only links\
                    to photos in markdown text, so specify your\
                    desired location (default: photos)')
    args_wip.add_argument(
            '--media-dir', metavar='media_dir',
            nargs='?', default='files',
            help='location of media files. this changes only links\
                    to files in markdown text, so specify your \
                    desired location (default: files)')

    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)s %(levelname)s %(name)s - %(message)s', level=args.log_level.upper())

    try:
        os.mkdir(args.out_dir)
    except FileExistsError:
        pass

    # load json file
    try:
        with open(args.json, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        sys.exit('result.json not found.\nPlease, specify right file')

    # load messages and user_id
    user_id = data['id']
    raw_posts = data['messages']

    for post in raw_posts:
        if post['type'] == 'message':

            post_date = datetime.fromisoformat(post['date'])
            post_filename = str(post_date.date()) + '-' + str(post['id']) + '.md'
            post_path = os.path.join(args.out_dir, post_filename)

            # https://github.com/telegramdesktop/tdesktop/blob/7e071c770f7691ffdbbbd38ac3e17c9aae4d21b3/Telegram/SourceFiles/export/data/export_data_types.cpp#L244
            # const auto text = QString::fromUtf8(data.v);
            with open(post_path, 'w', encoding='utf-8') as f:
                print(print_default_post_header(post, user_id), file=f)
                print(parse_post(post, args.photo_dir, args.media_dir), file=f)
        elif post['type'] == 'service' and post['action'] == 'clear_history':
            log.debug("The type of post #%i is 'service' and the action is 'clear_history'.")
            continue
        else:
            log.warning("The type of post #%i is '%s' and it is not supported.", post['id'], post['type'])

if __name__ == '__main__':
    main()
