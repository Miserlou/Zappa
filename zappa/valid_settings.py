from collections import defaultdict

ANY_SUBKEY_VALID = defaultdict(dict)

VALID_SETTINGS = {
	'api_key': {},
	'api_key_required': {},
	'apigateway_description': {},
	'apigateway_enabled': {},
	'app_function': {},
	'assume_policy': {},
	'async_resources': {},
	'async_response_table': {},
	'async_response_table_read_capacity': {},
	'async_response_table_write_capacity': {},
	'async_source': {},
	'attach_policy': {},
	'authorizer': {
		'arn': {},
        'function': {},
        'result_ttl': {},
        'token_source': {},
        'validation_expression': {}
	 },
	'aws_endpoint_urls': {
		'aws_service_name': {}
	},
	'aws_environment_variables': ANY_SUBKEY_VALID,
	'aws_kms_key_arn': {},
	'aws_region': {},
	'binary_support': {},
	'cache_cluster_enabled': {},
	'cache_cluster_encrypted': {},
	'cache_cluster_size': {},
	'cache_cluster_ttl': {},
	'callbacks': {
		'post': {},
       	'settings': {},
       	'zip': {}
    },
	'certificate': {},
	'certificate_arn': {},
	'certificate_chain': {},
	'certificate_key': {},
	'cloudwatch_data_trace': {},
	'cloudwatch_log_level': {},
	'cloudwatch_metrics_enabled': {},
	'context_header_mappings': ANY_SUBKEY_VALID,
	'cors': {},
	'dead_letter_arn': {},
	'debug': {},
	'delete_local_zip': {},
	'delete_s3_zip': {},
	'django_settings': {},
	'domain': {},
	'environment_variables': ANY_SUBKEY_VALID,
	'events': {
		'expression': {},
	    'function': {},
	    'event_source': {
	    	'arn': {},
	        'events': {},
	      	'function': {}
	    }
	 },
	'exception_handler': {},
	'exclude': ['*.gz', '*.rar'],
	'extends': {},
	'extra_permissions': {
		'Action': {},
		'Effect': {},
        'Resource': {}
     },
	'iam_authorization': {},
	'include': {},
	'keep_warm': {},
	'keep_warm_expression': {},
	'lambda_description': {},
	'lambda_handler': {},
	'lets_encrypt_key': {},
	'log_level': {},
	'manage_roles': {},
	'memory_size': {},
	'prebuild_script': {},
	'profile_name': {},
	'project_name': {},
	'remote_env': {},
	'remote_env_bucket': {},
	'remote_env_file': {},
	'role_name': {},
	'route53_enabled': {},
	'runtime': {},
	's3_bucket': {},
	'settings_file': {},
	'slim_handler': {},
	'tags': {},
	'timeout_seconds': {},
	'touch': {},
	'use_apigateway': {},
	'use_precompiled_packages': {},
	'vpc_config': {
		'SecurityGroupIds': {},
	    'SubnetIds': {}
	},
	'xray_tracing': {}
}