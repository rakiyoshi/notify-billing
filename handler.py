#!/usr/bin/env python

import os
import json
import boto3
from datetime import datetime, timedelta, date
from http.client import HTTPResponse
from urllib.request import Request, urlopen

def run(event, context):
    client = boto3.client('ce')
    total_billing = get_total_billings(client)
    service_billings = get_service_billings(client)
    message = get_message(total_billing, service_billings)
    url = get_webhook_url()
    response = post_slack(json.dumps(message, default=_json_serial), url)
    print(response)
    return 0


def get_total_billings(client) -> dict:
    (start_date, end_date) = _get_total_cost_date_range()
    response = client.get_cost_and_usage(
        TimePeriod={
            'Start': start_date,
            'End': end_date
        },
        Granularity='MONTHLY',
        Metrics=[
            'AmortizedCost'
        ]
    )
    return {
        'start': response['ResultsByTime'][0]['TimePeriod']['Start'],
        'end': response['ResultsByTime'][0]['TimePeriod']['End'],
        'billing': response['ResultsByTime'][0]['Total']['AmortizedCost']['Amount'],
    }


def get_service_billings(client):
    (start_date, end_date) = _get_total_cost_date_range()
    response = client.get_cost_and_usage(
        TimePeriod={
            'Start': start_date,
            'End': end_date
        },
        Granularity='MONTHLY',
        Metrics=[
            'AmortizedCost'
        ],
        GroupBy=[
            {
                'Type': 'DIMENSION',
                'Key': 'SERVICE'
            }
        ]
    )

    billings = []
    for item in response['ResultsByTime'][0]['Groups']:
        billings.append({
            'service_name': item['Keys'][0],
            'billing': item['Metrics']['AmortizedCost']['Amount']
        })
    return billings


def get_webhook_url() -> str:
    param_name = os.environ.get('WEBHOOKURL_PARAM_NAME')
    client = boto3.client('ssm')
    response = client.get_parameter(
        Name=param_name,
        WithDecryption=True
    )
    param = response.get('Parameter')
    if param:
        return param.get('Value')
    else:
        return None


def get_message(total_billing: dict, service_billings: list) -> dict:
    start = datetime.strptime(total_billing['start'], '%Y-%m-%d').strftime('%m/%d')
    end_today = datetime.strptime(total_billing['end'], '%Y-%m-%d')
    end_yesterday = (end_today - timedelta(days=1)).strftime('%m/%d')

    total = round(float(total_billing['billing']), 2)
    title = '{}～{}の請求額は、{} USDです。'.format(start, end_yesterday, total)
    details = []
    for item in service_billings:
        service_name = item['service_name']
        billing = round(float(item['billing']), 2)
        if billing == 0.0:
            continue
        details.append('- {}: {} USD'.format(service_name, billing))
    detail = '\n'.join(details)
    message = {
        'attachments': [
            {
                'color': 'good',
                'pretext': title,
                'text': detail
            }
        ]
    }
    return message


def post_slack(message: dict, webhookurl: str):
    request = Request(
        webhookurl,
        data=message.encode("utf-8"),
        method="POST"
    )
    with urlopen(request) as response:
        response_body = response.read().decode('utf-8')
    print('[send_message]response {}'.format(json.dumps(response_body, default=_json_serial)))


def _json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, HTTPResponse):
        return obj.read().decode('utf-8')
    raise TypeError ("Type %s is not serializable".format(type(obj)))


def _get_total_cost_date_range() -> (str, str):
    start_date = _get_begin_of_month()
    end_date = _get_today()
    if start_date == end_date:
        end_of_month = datetime.strptime(start_date, '%Y-%m-%d') + timedelta(days=-1)
        begin_of_month = end_of_month.replace(day=1)
        return begin_of_month.date().isoformat(), end_date
    else:
        return start_date, end_date


def _get_begin_of_month() -> str:
    return date.today().replace(day=1).isoformat()


def _get_today() -> str:
    return date.today().isoformat()


if __name__ == '__main__':
    run('', '')
