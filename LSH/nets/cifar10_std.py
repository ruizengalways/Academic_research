from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf
from nets import selu
import scipy.io as sio
from scipy.signal import convolve2d
import numpy as np
import cv2

slim = tf.contrib.slim
#trunc_normal = lambda stddev: tf.xavier_initializer()

def cifar10_std_arg_scope(weight_decay=0.0005):
    with slim.arg_scope([slim.conv2d],
                        weights_initializer=tf.contrib.layers.variance_scaling_initializer(),
                        biases_initializer=tf.zeros_initializer(),
                        weights_regularizer=slim.l2_regularizer(weight_decay)) as arg_sc:
        return arg_sc
def softmax(x,d):
    x_exp = tf.exp(x)
    return x_exp/tf.reduce_sum(x_exp,d,keep_dims=True)

def softmax_np(x,d):
    x_exp = np.exp(x)
    return x_exp/np.sum(x_exp,d,keepdims=True)


def convolve_np(x,f):
    x_sz = list(x.shape)
    x = x.reshape(x_sz+[1])
    f_sz = list(f.shape)
    f = f.reshape(f_sz[:2]+[1]+f_sz[2:])
    output = np.zeros((x_sz[0]+f_sz[0]-1,x_sz[0]+f_sz[0]-1,x_sz[2],f_sz[3]))
    x = np.pad(x,(((f_sz[0]-1),(f_sz[0]-1)),((f_sz[0]-1),(f_sz[0]-1)),(0,0),(0,0),(0,0)),'constant')
    for i in range(output.shape[0]):
        for j in range(output.shape[1]):
            output[i,j] = np.sum(x[i:i+f_sz[0],j:j+f_sz[1]]*f,(0,1,3))
    return output

def pooling_np(x,f):
    x_sz = list(x.shape)
    f_sz = list(f.shape)
    f = f.reshape(f_sz[:2]+[1]+f_sz[2:])
    output = np.zeros((x_sz[0]+f_sz[0]-1,x_sz[0]+f_sz[0]-1,x_sz[2],x_sz[3]))
    x = np.pad(x,(((f_sz[0]-1),(f_sz[0]-1)),((f_sz[0]-1),(f_sz[0]-1)),(0,0),(0,0)),'constant')
    for i in range(output.shape[0]):
        for j in range(output.shape[1]):
            output[i,j] = np.mean(x[i:i+f_sz[0],j:j+f_sz[1]],(0,1))
    return output

def dist_init(filters, shape=[1,1]):
    num_in = len(filters)
    
    f = filters[0]
    for n in range(1,num_in):
        if len(filters[n].shape)==4:
            f = convolve_np(f,np.float32(filters[n]))
        else:
            f = pooling_np(f,np.float32(filters[n]))
        
    output = np.zeros([shape[0],shape[1],f.shape[2],f.shape[3]],dtype=np.float32)
    for n in range(output.shape[-1]):
        output[:,:,:,n] = cv2.resize(f[:,:,:,n], (shape[0],shape[1]),interpolation=cv2.INTER_CUBIC)
        
#    output = np.transpose(output,[1,2,0,3])
    
    
    if shape[0] == 1:
        output = np.squeeze(output)
    return output

def active_map(x,d):
    with tf.variable_scope('Active_map'):
        sz = x.get_shape().as_list()
        w = 1
        for i in d:
            w*=sz[i]
        x = softmax(x,d)*w
#        x = x*softmax(x,3)*sz[3]
    return x
def RBF(x,y):
    with tf.variable_scope('RBF'):
        x_sz = x.get_shape().as_list()                
        y_sz = y.get_shape().as_list()
        
#        x = 
#        x *= active_map(x,[1,2])
        x_re = tf.reduce_sum(x,[1,2])
        x_re = tf.reshape(x_re,[x_sz[0],1,x_sz[3]])
        
#        y *= active_map(y,[1,2])
        y_re = tf.reduce_sum(y,[1,2])
        y_re = tf.reshape(y_re,[y_sz[0],1,y_sz[3]])
        
        x_sz = x_re.get_shape().as_list()        
        y_sz = y_re.get_shape().as_list()
        
        x_exp = []
        for i in range(x_sz[2]):
            x_l2 = tf.reduce_sum(tf.square( tf.slice(x_re,[0,0,i],[x_sz[0],x_sz[1],1])-y_re),1,keep_dims=True)
            x_exp.append(tf.exp(-x_l2/8))
    
        rbf = tf.concat(x_exp,1)
    return rbf



def gram_matrix(x,y):
    with tf.variable_scope('Gram'):
        dim_x = x.get_shape().as_list()
        if len(dim_x)>3:            
            x = tf.reshape(x, [dim_x[0], dim_x[1]*dim_x[2],dim_x[3]])
            dim_x = x.get_shape().as_list()
        
        dim_y = y.get_shape().as_list()
        
        
        if len(dim_y)>3:
            y = tf.reshape(y, [dim_y[0], dim_y[1]*dim_y[2],dim_y[3]])
            dim_y = y.get_shape().as_list()
#        y = tf.reshape(y, [dim_y[0], dim_y[1], dim_y[3]])
        gram = tf.matmul(x, y, transpose_a=True)/(dim_x[2]*dim_y[2])
#        gram = gram*active_map(gram,[1])*active_map(gram,[2])
        return gram
def cifar10_std(image, is_training=False, val = False, lr = None, prediction_fn=slim.softmax,scope='cifar10'):
    end_points = {}
    large = sio.loadmat('/home/dmsl/nas/share/training/cifar112/vgg-m.mat')
    with tf.variable_scope(scope, 'cifar10', [image]):
        conv = slim.conv2d(image, 96, [5, 5], 4, padding = 'VALID', activation_fn=None,
                           weights_initializer = tf.constant_initializer(dist_init([large['conv1w'],np.ones((3,3))/(3*3)],[5,5])),
##                           weights_initializer = tf.constant_initializer(large['conv1w']),
                           biases_initializer  = tf.constant_initializer(large['conv1b']),
                           scope='conv1', trainable=is_training, reuse=val)                
        std0 = tf.nn.relu(conv)
        std0 = tf.nn.lrn(std0)
#        std0 = slim.max_pool2d(std0, [3, 3], 2, scope='pool1')
        
        conv = slim.conv2d(std0, 256, [3, 3], 4, padding = 'VALID', activation_fn=None,
                           weights_initializer = tf.constant_initializer(dist_init([large['conv2w'],np.ones((3,3))/(3*3)],[3,3])),
                           biases_initializer  = tf.constant_initializer(large['conv2b']),
                           scope='conv2', trainable=is_training, reuse=val)        
        std1 = tf.nn.relu(conv)
        std1 = tf.nn.lrn(std1)
        
        conv = slim.conv2d(std1, 512, [3, 3], 2, padding = 'VALID', activation_fn=None,
                           weights_initializer = tf.constant_initializer(dist_init([large['conv3w']],[3,3])),
                           biases_initializer  = tf.constant_initializer(large['conv3b']),
#                           weights_initializer = tf.constant_initializer(large['conv3w']),
#                           biases_initializer  = tf.constant_initializer(large['conv3b']),
                           scope='conv3', trainable=is_training, reuse=val)
        std2 = tf.nn.relu(conv)
        
        conv = tf.contrib.layers.flatten(std2)
        fc1 = slim.fully_connected(conv, 512, activation_fn=tf.nn.relu,
                                   weights_initializer = tf.constant_initializer(dist_init([large['fc4w'].reshape(1,1,512*9,512),large['fc5w'].reshape(1,1,512,512)])),
                                   biases_initializer  = tf.constant_initializer(dist_init([large['fc4b'].reshape(1,1,1,512),large['fc5w'].reshape(1,1,512,512)])+large['fc5b']),
                                   trainable=is_training, scope = 'full1', reuse = val)
        fc = slim.dropout(fc1,0.5,is_training=is_training)
        logits = slim.fully_connected(fc, 100, activation_fn=None,
#                                      weights_initializer = tf.constant_initializer([large['fc6w']]),
                                      weights_initializer = tf.constant_initializer(large['fc6w']),
                                      biases_initializer  = tf.constant_initializer(large['fc6b']),
                                      trainable=is_training, scope = 'full3', reuse = val)
        
        
        
        if is_training:
            with tf.variable_scope('teacher'):
                conv = slim.conv2d(image, 96, [7, 7], 2, padding = 'VALID', activation_fn=tf.nn.relu,
                                   weights_initializer = tf.constant_initializer(large['conv1w']),
                                   biases_initializer  = tf.constant_initializer(large['conv1b']),
                                   scope='convt1', trainable=False, reuse=False)        
                conv = tf.nn.lrn(conv)
                teach0 = slim.max_pool2d(conv, [3, 3], 2, scope='pool1')
                
                conv = slim.conv2d(teach0, 256, [5, 5], 2, padding = 'VALID', activation_fn=tf.nn.relu,
                                   weights_initializer = tf.constant_initializer(large['conv2w']),
                                   biases_initializer  = tf.constant_initializer(large['conv2b']),
                                   scope='convt2', trainable=False, reuse=False)        
                conv = tf.nn.lrn(conv)
                teach1 = slim.max_pool2d(conv, [3, 3], 2, scope='pool2')
                teach2 = slim.conv2d(teach1, 512, [3, 3], 1, padding = 'VALID', activation_fn=tf.nn.relu,
                                   weights_initializer = tf.constant_initializer(large['conv3w']),
                                   biases_initializer  = tf.constant_initializer(large['conv3b']),
                                   scope='convt3', trainable=False, reuse=False)
                
                conv = tf.contrib.layers.flatten(teach2)
                fct1 = slim.fully_connected(conv, 512, activation_fn=tf.nn.relu,
                                           weights_initializer = tf.constant_initializer(large['fc4w']),
                                           biases_initializer  = tf.constant_initializer(large['fc4b']),
                                           trainable=False, scope = 'fullt1', reuse = False)
                fct2 = slim.fully_connected(fct1, 512, activation_fn=tf.nn.relu,
                                           weights_initializer = tf.constant_initializer(large['fc5w']),
                                           biases_initializer  = tf.constant_initializer(large['fc5b']),
                                           trainable=False, scope = 'fullt2', reuse = False)
                with tf.variable_scope('rbf_grammian'):
#                    std0 = active_map(std0,[3])
#                    std1 = active_map(std1,[3])
#                    std2 = active_map(std2,[3])
#                    act0 = active_map(teach0,[3])
#                    act1 = active_map(teach1,[3])
#                    act2 = active_map(teach2,[3])
#                    act3 = active_map(fct2,[1])
#                    
#                    std0 *= act0
#                    std1 *= act1
#                    std2 *= act2
#                    fc1 *= act3
#                    
#                    teach0 *= act0
#                    teach1 *= act1
#                    teach2 *= act2
#                    fct2 *= act3
                    
                    dim_std2 = std2.get_shape().as_list()
                    
                    rbfc_s = []
                    rbfc_s.append(RBF(std0,std1))
                    rbfc_s.append(RBF(std0,std2))
                    rbfc_s.append(RBF(std0,tf.reshape(fc1,[dim_std2[0],1,1,512])))
                    rbfc_s.append(RBF(std1,std2))
                    rbfc_s.append(RBF(std1,tf.reshape(fc1,[dim_std2[0],1,1,512])))
                    rbfc_s.append(RBF(std2,tf.reshape(fc1,[dim_std2[0],1,1,512])))
                    
                    rbfc_t = []
                    rbfc_t.append(RBF(teach0,teach1))
                    rbfc_t.append(RBF(teach0,teach2))
                    rbfc_t.append(RBF(teach0,tf.reshape(fct2,[dim_std2[0],1,1,512])))
                    rbfc_t.append(RBF(teach1,teach2))
                    rbfc_t.append(RBF(teach1,tf.reshape(fct2,[dim_std2[0],1,1,512])))
                    rbfc_t.append(RBF(teach2,tf.reshape(fct2,[dim_std2[0],1,1,512])))
                    
#                    rbfc_s01 = gram_matrix(tf.reduce_sum(std0,[1,2],keep_dims=True),tf.reduce_sum(std1,[1,2],keep_dims=True))
##                    rbfc_s02 = gram_matrix(tf.reduce_sum(std0,[1,2],keep_dims=True),tf.reduce_sum(std2,[1,2],keep_dims=True))
#                    rbfc_s12 = gram_matrix(tf.reduce_sum(std1,[1,2],keep_dims=True),tf.reduce_sum(std2,[1,2],keep_dims=True))
#                    rbfc_s23 = gram_matrix(tf.reduce_sum(std2,[1,2],keep_dims=True),tf.reshape(fc1,[dim_std2[0],1,1,512]))                    
#                    
#                    rbfc_t01 = gram_matrix(tf.reduce_sum(teach0,[1,2],keep_dims=True),tf.reduce_sum(teach1,[1,2],keep_dims=True))
##                    rbfc_t02 = gram_matrix(tf.reduce_sum(teach0,[1,2],keep_dims=True),tf.reduce_sum(teach2,[1,2],keep_dims=True))
#                    rbfc_t12 = gram_matrix(tf.reduce_sum(teach1,[1,2],keep_dims=True),tf.reduce_sum(teach2,[1,2],keep_dims=True))
#                    rbfc_t23 = gram_matrix(tf.reduce_sum(teach2,[1,2],keep_dims=True),tf.reshape(fct2,[dim_std2[0],1,1,512]))  
                    
                    for i in range(6):
                        if i == 0:
                           act = active_map(rbfc_t[i],[2])
                           dist_loss = tf.nn.l2_loss(rbfc_s[i]*act-rbfc_t[i]*act)
                           
                        act = active_map(rbfc_t[i],[2])
                        dist_loss = tf.nn.l2_loss(rbfc_s[i]*act-rbfc_t[i]*act)
                        
#                    act0 = active_map(rbfc_t01,[1])
#                    act1 = active_map(rbfc_t12,[1])
#                    act2 = active_map(rbfc_t23,[1])
#                    rbfc_s01 *= act0
#                    rbfc_s12 *= act1
#                    rbfc_s23 *= act2
#                    
#                    rbfc_t01 *= act0
#                    rbfc_t12 *= act1
#                    rbfc_t23 *= act2
#                    
#                    dist_loss3 = tf.nn.l2_loss(rbfc_s01-rbfc_t01)
#                    dist_loss4 = tf.nn.l2_loss(rbfc_s02-rbfc_t02)
#                    dist_loss5 = tf.nn.l2_loss(rbfc_s12-rbfc_t12)
#                    dist_loss6 = tf.nn.l2_loss(rbfc_s23-rbfc_t23)
#                    
#                    dist_loss7 = tf.nn.l2_loss(rbfc_s03-rbfc_t03)
#                    dist_loss8 = tf.nn.l2_loss(rbfc_s13-rbfc_t13)
                    
                    end_points['Dist'] = dist_loss/(96*(256+512+512)+256*(512+512)+512*512)
            
        
    end_points['Logits1'] = logits
    return end_points
cifar10_std.default_image_size = 32
