import argparse
import gym
from gym import wrappers
import os.path as osp
import random
import numpy as np

import torch
import torch.nn as nn

import dqn_pt
from dqn_utils import *
from atari_wrappers import *


class BatchFlatten(nn.Module):
    def __init__(self):
        super(BatchFlatten, self).__init__()

    def forward(self, x):
        return x.view(x.size(0), -1)


class Conv2DRelu(nn.Conv2d):
    def __init__(self, *args, **kwargs):
        super(Conv2DRelu, self).__init__(*args, **kwargs)
        self.lr = nn.ReLU()

    def forward(self, x):
        x = super(ConvBatchLeaky, self).forward(x)
        return self.lr(x)


class AtariModel(nn.Module):
    def __init__(self, input_shape, num_actions):
        super(AtariModel, self).__init__()
        self.c1 = Conv2DRelu(input_shape, 32, 8, 4, 1)
        self.c2 = Conv2DRelu(32, 64, 4, 2, 1)
        self.c3 = Conv2DRelu(64, 64, 3, 1, 1)
        self.bf = BatchFlatten()
        self.fc1 = nn.Linear(7 * 7 * 64, 512)
        self.fc2 = nn.Linear(512, num_actions)

    def forward(self, x):
        x = self.c1(x)
        x = self.c2(x)
        x = self.c3(x)
        x = self.bf(x)
        x = F.ReLU(self.fc1(x))
        x = self.fc2(x)
        return x


# def atari_model(img_in, num_actions, scope, reuse=False):
#     # as described in https://storage.googleapis.com/deepmind-data/assets/papers/DeepMindNature14236Paper.pdf
#     with tf.variable_scope(scope, reuse=reuse):
#         out = img_in
#         with tf.variable_scope("convnet"):
#             # original architecture
#             out = layers.convolution2d(out, num_outputs=32, kernel_size=8, stride=4, activation_fn=tf.nn.relu)
#             out = layers.convolution2d(out, num_outputs=64, kernel_size=4, stride=2, activation_fn=tf.nn.relu)
#             out = layers.convolution2d(out, num_outputs=64, kernel_size=3, stride=1, activation_fn=tf.nn.relu)
#         out = layers.flatten(out)
#         with tf.variable_scope("action_value"):
#             out = layers.fully_connected(out, num_outputs=512, activation_fn=tf.nn.relu)
#             out = layers.fully_connected(out, num_outputs=num_actions, activation_fn=None)

#         return out


def atari_learn(env,
                session,
                num_timesteps):
    # This is just a rough estimate
    num_iterations = float(num_timesteps) / 4.0

    lr_multiplier = 1.0
    lr_schedule = PiecewiseSchedule([
        (0, 1e-4 * lr_multiplier),
        (num_iterations / 10, 1e-4 * lr_multiplier),
        (num_iterations / 2, 5e-5 * lr_multiplier),
    ],
        outside_value=5e-5 * lr_multiplier)



    atari_model = AtariModel()

    optimizer = dqn_pt.OptimizerSpec(
        constructor=torch.optim.Adam(atari_model.parameters(), 1e-3, weight_decay=1e-4),
        kwargs=dict(epsilon=1e-4),
        lr_schedule=lr_schedule
    )

    def stopping_criterion(env, t):
        # notice that here t is the number of steps of the wrapped env,
        # which is different from the number of steps in the underlying env
        return get_wrapper_by_name(env, "Monitor").get_total_steps() >= num_timesteps

    exploration_schedule = PiecewiseSchedule(
        [
            (0, 1.0),
            (1e6, 0.1),
            (num_iterations / 2, 0.01),
        ], outside_value=0.01
    )

    dqn_pt.learn(
        env=env,
        q_func=atari_model,
        optimizer_spec=optimizer,
        session=session,
        exploration=exploration_schedule,
        stopping_criterion=stopping_criterion,
        replay_buffer_size=1000000,
        batch_size=32,
        gamma=0.99,
        learning_starts=50000,
        learning_freq=4,
        frame_history_len=4,
        target_update_freq=10000,
        grad_norm_clipping=10,
        double_q=True
    )
    env.close()


def get_available_gpus():
    from tensorflow.python.client import device_lib
    local_device_protos = device_lib.list_local_devices()
    return [x.physical_device_desc for x in local_device_protos if x.device_type == 'GPU']


def set_global_seeds(i):
    try:
        import tensorflow as tf
    except ImportError:
        pass
    else:
        tf.set_random_seed(i)
    np.random.seed(i)
    random.seed(i)


def get_session():
    tf.reset_default_graph()
    tf_config = tf.ConfigProto(
        inter_op_parallelism_threads=1,
        intra_op_parallelism_threads=1)
    session = tf.Session(config=tf_config)
    print("AVAILABLE GPUS: ", get_available_gpus())
    return session


def get_env(task, seed):
    env = gym.make('PongNoFrameskip-v4')

    set_global_seeds(seed)
    env.seed(seed)

    expt_dir = '/tmp/hw3_vid_dir2/'
    env = wrappers.Monitor(env, osp.join(expt_dir, "gym"), force=True)
    env = wrap_deepmind(env)

    return env


def main():
    # Get Atari games.
    task = gym.make('PongNoFrameskip-v4')

    # Run training
    seed = random.randint(0, 9999)
    print('random seed = %d' % seed)
    env = get_env(task, seed)
    session = get_session()
    atari_learn(env, session, num_timesteps=2e8)


if __name__ == "__main__":
    main()
