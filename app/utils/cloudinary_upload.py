import cloudinary
import cloudinary.uploader
import os

cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET')
)

def upload_vehicle_image(file, salesperson_id, vehicle_id=None):
    """Upload a vehicle image to Cloudinary and return the URL."""
    try:
        folder = f"carsinstock/{salesperson_id}"
        if vehicle_id:
            folder = f"carsinstock/{salesperson_id}/{vehicle_id}"
        
        result = cloudinary.uploader.upload(
            file,
            folder=folder,
            transformation=[
                {'width': 800, 'height': 600, 'crop': 'limit', 'quality': 'auto'}
            ]
        )
        print(f"Image uploaded: {result['secure_url']}")
        return result['secure_url']
    except Exception as e:
        print(f"Cloudinary error: {e}")
        return None
