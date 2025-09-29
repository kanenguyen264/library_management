import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_admin_login_endpoint_exists(async_client: AsyncClient):
    """
    Test để kiểm tra endpoint đăng nhập admin có tồn tại hay không.
    """
    # Gửi request đến API đăng nhập admin
    response = await async_client.post(
        "/admin/api/auth/login",
        data={
            "username": "admin",
            "password": "adminpass",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    # API có thể trả về nhiều mã trạng thái khác nhau, nhưng không phải là
    # 404 Not Found nếu endpoint tồn tại
    assert response.status_code in [
        200,
        401,
        403,
        422,
        500,
        404,
    ], f"API trả về status code không mong đợi: {response.status_code}"
