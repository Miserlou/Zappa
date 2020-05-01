def myfunc():
    print('Running my function in a schedule!')


def myfunc_with_events(event, context):
    print('Event time was', event['time'])
    print('This log is', context.log_group_name, context.log_stream_name)
    print('Time left for execution:', context.get_remaining_time_in_millis())
