import numpy as np
import cv2
from scipy.interpolate import griddata
import plyfile

plyfile.





# disparity, depthmap, image3d to pointcloud
o3d.loa
# pointcloud to disparity, depthmap, image3d

def image_3d_to_pointcloud(image_3d):





def depthmap_to_image_3d(depthmap, K, D=np.zeros((5,1))):
    """Converts one depthmap to xyz image.
    
    Given a Depthmap this functions reprojects points to 3d using the calibration
    parameteres provided. for a location (u,v), a depthmap stores the length of
    the vector starting from the camera center and ending to a point in 3D which
    projects to (u,v). Using the camera parameteres we can get the 3d direction
    of those vectors and then normalize their length accorind to the depthmap
    in order to compute the 3d geometry captured in the image. the function 
    outputs this information as a 3 channel image, with each channel representing
    a 3d component, namely X,Y,Z in this order.
    Args:
        depthmap (np.ndarray): depthamp image with dimentrion of hxw
        K (np.ndarray): Camera matrix 
        D (np.ndarray): Camera Distortion coefficients

    Returns:
        np.ndarray: xyz image of dimentions hxwx3
    """
    #create a with pixel locations as values vectorsize it and make it pixel homogeneous
    h,w = depthmap.shape[:2]
    pixel_loc = np.mgrid[0:w,0:h].transpose(2,1,0).astype(np.float)
    pixel_loc=pixel_loc.reshape(-1,2)
    
    # project pixels in the image
    image_plane_pts = cv2.undistortPoints(pixel_loc, K, D).squeeze()
    image_plane_pts_h = np.hstack((image_plane_pts, np.ones((image_plane_pts.shape[0],1))))
    
    #normalize and multiply by depth
    norm = np.sqrt(np.sum(image_plane_pts_h**2,axis=1)).reshape(-1,1)
    image_plane_pts_h_norm=image_plane_pts_h / norm
    xyz_map = image_plane_pts_h_norm * depthmap.reshape(-1,1)

    return xyz_map.reshape(h,w,3)


def image_3d_to_depthmap(image_3d):
    """covert 3 channel xyz image to 1 channel depthmap

    Args:
        image_3d (np.ndarray): hxwx3 xyz image, each image point encodes the 3d
        location of the point is the projection of.

    Returns:
        np.ndarray: hxw depthmap.
    """
    return image_3d[:,:,2]

def pts3d_to_depthmap(pts3d, K, D, size):
    """create depthmap projecting 3d points to an image location at origin, 
    defined by camera matrix K with distortion coefficients D and size=size

    Args:
        pts3d (np.ndarray): Nx3 Nx3 array containing 3d points
        K (np.ndarray): camera matrix.
        D (np.ndarray): distortion coefficients.
        size (tuple): size of the resulting disparity image hxw
    Returns:
        np.ndarray: hxw depthmap. each element is the length of the vector 
        starting from camera center and end up in a point in 3d. Each such vector
        passes through a pixel in image plane. 
    """
    h,w = size
    depthmap =np.zeros((h,w))
    scared_depthmap =np.zeros((h,w,3))
    img_pts = cv2.projectPoints(pts3d, np.eye(3), np.zeros(3), K, D)[0].squeeze()
    
    img_pts = np.round(img_pts)
    valid_indexes=((img_pts[:,0]>=0) & (img_pts[:,0]<w) & (img_pts[:,1]>=0) & (img_pts[:,1]<h))
    depthmap_idxs = img_pts[valid_indexes].astype(int)
    valid_pts3d = pts3d[valid_indexes]
    xs,ys = depthmap_idxs[:,0], depthmap_idxs[:,1]
    scared_depthmap[ys,xs]=valid_pts3d
    scared_depthmap.reshape(h,w,3)
    depthmap = scared_to_depthmap(scared_depthmap)


    return depthmap, scared_depthmap

def ptd3d_to_disparity(pts_3d, P1, P2, size):
    """create disparity images based on pts_3d and projection matrices of
    rectified views.

    Args:
        pts_3d (np.ndarray): Nx3 array containing 3d points
        P1 (np.ndarray): projection matrix of left rectified view
        P2 (np.ndarray): projection matrix of right rectified view
        size (tuple): size of the resulting disparity image hxw

    Returns:
        np.ndarray: disparity image.
    """
    
    h,w=size
    disparity_img = np.zeros(size)
    
    left_projection = project_pts(pts_3d, P1).reshape(-1,2)
    right_projection = project_pts(pts_3d, P2).reshape(-1,2)
    left_projection = np.nan_to_num(left_projection, nan=-1.0) #supress warnings
    disparities = (left_projection-right_projection)[:,0]
    
    #find all points that project inside the image domain.
    left_projection = np.round(left_projection)
    valid_indexes=((left_projection[:,0]>=0) & (left_projection[:,0]<w) & (left_projection[:,1]>=0) & (left_projection[:,1]<h))
    
    disparity_idxs = left_projection[valid_indexes].astype(int)
    valid_disparities = disparities[valid_indexes]

    xs,ys = disparity_idxs[:,0], disparity_idxs[:,1]

    disparity_img[ys,xs]=valid_disparities
    
    return disparity_img

def disparity_to_original_scared(disparity, calib):
    """convert disparity image from left rectified frame to scared depthmap in 
    the original frame

    Args:
        disparity (np.ndarray): disparity image in the left rectified frame
        calib (dict): calibration dictionary containing rectification parameters

    Returns:
        np.ndarray: 3d image scared depthmap expressed in the original left frame
        with distortions, to be directly evaluated with ground truth.
    """
    
    h,w= disparity.shape[:2]
    scared_depthmap =np.zeros((h,w, 3))
    pts3d = cv2.reprojectImageTo3D(disparity, calib['Q'])
    pts3d = pts3d.reshape(-1,3)
    #rotate it by inv R1 to align it with the left original frame
    pts3d = np.nan_to_num(pts3d) # to avoid warnings when mulitpling 
    pts3d = transform_pts(pts3d, create_RT(R = np.linalg.inv(calib['R1'])))
    img_pts = cv2.projectPoints(pts3d, np.eye(3), np.zeros(3), calib['K1'], calib['D1'])[0].squeeze()
    
    img_pts = np.round(img_pts)
    valid_indexes=((img_pts[:,0]>=0) & (img_pts[:,0]<w) & (img_pts[:,1]>=0) & (img_pts[:,1]<h))
    depthmap_idxs = img_pts[valid_indexes].astype(int)
    valid_pts3d = pts3d[valid_indexes]
    xs,ys = depthmap_idxs[:,0], depthmap_idxs[:,1]
    scared_depthmap[ys,xs]=valid_pts3d
    return scared_depthmap


def project_pts(pts3d, P):
    """project 3d points to image, according to projection matrix P

    Args:
        pts3d (np.ndarray): Nx3 array containing 3d points
        P (np.ndarray): projection matrix

    Returns:
        np.ndarray: Nx2 array containing pixel coordinates of projected points.
    """
    # convert to homogeneous
    pts3d_h = np.hstack((pts3d, np.ones((pts3d.shape[0],1))))
    projected_pts = (P @ pts3d_h.T).T
    # convert from homogeneous
    projected_pts = projected_pts[:,:2]/projected_pts[:,2].reshape(-1,1)
    return projected_pts

def transform_pts(pts3d, RT):
    """transform points using RT homogeneous matrix

    Args:
        pts3d (np.ndarray): Nx3 array containin 3d point coordinates
        RT (np.ndarray): 4x4 homogeneous transformation matrix

    Returns:
        np.ndarray: Nx3 transformed pts3d points according to RT
    """
    pts3d_h = np.hstack((pts3d, np.ones((pts3d.shape[0],1))))
    rotated_pts3d_h = (RT @ pts3d_h.T).T
    rotated_pts3d = rotated_pts3d_h[:,:3] / (rotated_pts3d_h[:,3].reshape(-1,1))
    return rotated_pts3d

def create_RT(R=np.eye(3), T=np.zeros(3)):
    """Create 4x4 homogeneous transformation matrix

    Args:
        R (np.ndarray, optional): 3x3 rotation matrix. Defaults to np.eye(3).
        T (np.ndarray, optional): translation vector. Defaults to np.zeros(3).

    Returns:
        np.ndarray: 4x4 homogeneous transformation matrix
    """
    RT =np.eye(4)
    RT[:3,:3]= R.copy()
    RT[:3,3] = T.reshape(3).copy()
    return RT

def interpolate_missing_1ch(img_1ch):
    a = img_1ch.copy()
    a[a==0]=np.nan

    #interpolate zero values if possible.
    x, y = np.indices(a.shape)
    interp = np.array(a)
    interp[np.isnan(interp)] = griddata(
        (x[~np.isnan(a)], y[~np.isnan(a)]), # points we know
        a[~np.isnan(a)],                    # values we know
        (x[np.isnan(a)], y[np.isnan(a)]))   # points to interpolate
    return interp
    