from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from app.services import aws_tools


def test_list_s3_buckets_success(mocker, fake_credentials) -> None:
    s3 = MagicMock()
    s3.list_buckets.return_value = {
        "Buckets": [{"Name": "logs"}, {"Name": "artifacts"}]
    }
    mocker.patch.object(aws_tools.boto3, "client", return_value=s3)

    result = aws_tools.list_s3_buckets.invoke(
        {
            "aws_access_key_id": fake_credentials["aws_access_key_id"],
            "aws_secret_access_key": fake_credentials[
                "aws_secret_access_key"
            ],
        }
    )

    assert result == ["logs", "artifacts"]


def test_list_s3_buckets_invalid_credentials(
    mocker, fake_credentials
) -> None:
    s3 = MagicMock()
    s3.list_buckets.side_effect = ClientError(
        {
            "Error": {
                "Code": "InvalidAccessKeyId",
                "Message": "The AWS Access Key Id does not exist.",
            }
        },
        "ListBuckets",
    )
    mocker.patch.object(aws_tools.boto3, "client", return_value=s3)

    with pytest.raises(ClientError) as exc_info:
        aws_tools.list_s3_buckets.invoke(
            {
                "aws_access_key_id": fake_credentials["aws_access_key_id"],
                "aws_secret_access_key": fake_credentials[
                    "aws_secret_access_key"
                ],
            }
        )

    assert exc_info.value.response["Error"]["Code"] == "InvalidAccessKeyId"


def test_create_s3_bucket_success(mocker, fake_credentials) -> None:
    s3 = MagicMock()
    mocker.patch.object(aws_tools.boto3, "client", return_value=s3)

    result = aws_tools.create_s3_bucket.invoke(
        {**fake_credentials, "bucket_name": "test-automation-bucket"}
    )

    assert result.status == "success"
    s3.create_bucket.assert_called_once_with(
        Bucket="test-automation-bucket"
    )


def test_create_ec2_instance_uses_region_from_input(
    mocker, fake_credentials
) -> None:
    ec2 = MagicMock()
    ec2.run_instances.return_value = {
        "Instances": [{"InstanceId": "i-0123456789"}]
    }
    client = mocker.patch.object(
        aws_tools.boto3, "client", return_value=ec2
    )
    mocker.patch.object(aws_tools, "get_ami_id", return_value="ami-test")
    mocker.patch.object(
        aws_tools, "create_default_security_group", return_value="sg-test"
    )

    aws_tools.create_ec2_instance.invoke(
        {
            **fake_credentials,
            "friendly_name": "Amazon Linux",
            "instance_type": "t3.micro",
            "min_count": 1,
            "max_count": 1,
        }
    )

    client.assert_called_once_with(
        "ec2",
        aws_access_key_id="AKIATEST",
        aws_secret_access_key="fakesecret",
        region_name="us-east-1",
    )


def test_credential_naming_consistency() -> None:
    for aws_tool in aws_tools.get_all_aws_tools():
        fields = set(aws_tool.args_schema.model_fields)
        assert "aws_access_key_id" in fields, aws_tool.name
        assert "aws_secret_access_key" in fields, aws_tool.name
        assert "AWS_ACCESS_KEY_ID" not in fields, aws_tool.name
        assert "AWS_SECRET_ACCESS_KEY" not in fields, aws_tool.name
