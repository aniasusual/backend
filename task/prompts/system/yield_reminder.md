{% if budget_stop %}
Soft request budget reached. You MUST now conclude your work and call `yield` with your final findings or summary immediately.
{% else %}
Reminder ({{ retry_count }}/{{ max_retries }}): You have completed tool actions but did not call `yield`. 
You MUST call the `yield` tool now to deliver your report and conclude this assignment.
{% endif %}
