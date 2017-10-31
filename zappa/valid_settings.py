from collections import defaultdict

ANY_SUBKEY_VALID = defaultdict(None)

VALID_SETTINGS = {
	'api_key': None,
	'api_key_required': None,
	'apigateway_description': None,
	'apigateway_enabled': None,
	'app_function': None,
	'assume_policy': None,
	'async_resources': None,
	'async_response_table': None,
	'async_response_table_read_capacity': None,
	'async_response_table_write_capacity': None,
	'async_source': None,
	'attach_policy': None,
	'authorizer': {
		'arn': None,
        'function': None,
        'result_ttl': None,
        'token_source': None,
        'validation_expression': None
	 },
	'aws_endpoint_urls': {
		'aws_service_name': None
	},
	'aws_environment_variables': ANY_SUBKEY_VALID,
	'aws_kms_key_arn': None,
	'aws_region': None,
	'binary_support': None,
	'cache_cluster_enabled': None,
	'cache_cluster_encrypted': None,
	'cache_cluster_size': None,
	'cache_cluster_ttl': None,
	'callbacks': {
		'post': None,
       	'settings': None,
       	'zip': None
    },
	'certificate': None,
	'certificate_arn': None,
	'certificate_chain': None,
	'certificate_key': None,
	'cloudwatch_data_trace': None,
	'cloudwatch_log_level': None,
	'cloudwatch_metrics_enabled': None,
	'context_header_mappings': ANY_SUBKEY_VALID,
	'cors': None,
	'dead_letter_arn': None,
	'debug': None,
	'delete_local_zip': None,
	'delete_s3_zip': None,
	'django_settings': None,
	'domain': None,
	'environment_variables': ANY_SUBKEY_VALID,
	'events': {
		'expression': None,
	    'function': None,
	    'event_source': {
	    	'arn': None,
	        'events': None,
	      	'function': None
	    }
	 },
	'exception_handler': None,
	'exclude': ['*.gz', '*.rar'],
	'extends': None,
	'extra_permissions': {
		'Action': None,
		'Effect': None,
        'Resource': None
     },
	'iam_authorization': None,
	'include': None,
	'keep_warm': None,
	'keep_warm_expression': None,
	'lambda_description': None,
	'lambda_handler': None,
	'lets_encrypt_key': None,
	'log_level': None,
	'manage_roles': None,
	'memory_size': None,
	'prebuild_script': None,
	'profile_name': None,
	'project_name': None,
	'remote_env': None,
	'remote_env_bucket': None,
	'remote_env_file': None,
	'role_name': None,
	'route53_enabled': None,
	'runtime': None,
	's3_bucket': None,
	'settings_file': None,
	'slim_handler': None,
	'tags': None,
	'timeout_seconds': None,
	'touch': None,
	'use_apigateway': None,
	'use_precompiled_packages': None,
	'vpc_config': {
		'SecurityGroupIds': None,
	    'SubnetIds': None
	},
	'xray_tracing': None
}