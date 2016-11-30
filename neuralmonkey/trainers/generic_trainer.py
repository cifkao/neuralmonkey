from typing import Any, Dict, List, NamedTuple, Optional, Tuple
import re

import tensorflow as tf

from neuralmonkey.runners.base_runner import (collect_encoders, Executable,
                                              ExecutionResult, NextExecute)

# tests: lint, mypy

# pylint: disable=invalid-name
Gradients = List[Tuple[tf.Tensor, tf.Variable]]
Objective = NamedTuple('Objective',
                       [('name', str),
                        ('decoder', Any),
                        ('loss', tf.Tensor),
                        ('gradients', Optional[Gradients])])

BIAS_REGEX = re.compile(r'[Bb]ias')


# pylint: disable=too-few-public-methods,too-many-locals
class GenericTrainer(object):

    def __init__(self, objectives: List[Objective],
                 l1_weight=0.0, l2_weight=0.0,
                 clip_norm=False, optimizer=None) -> None:

        if optimizer is None:
            self.optimizer = tf.train.AdamOptimizer(1e-4)
        else:
            self.optimizer = optimizer

        with tf.variable_scope('regularization'):
            regularizable = [tf.reduce_sum(
                v ** 2) for v in tf.trainable_variables()
                             if BIAS_REGEX.findall(v.name)]
            l1_value = sum(abs(v) for v in regularizable)
            l1_cost = l1_weight * l1_value if l1_weight > 0 else 0.0

            l2_value = sum(v * v for v in regularizable)
            l2_cost = l2_weight * l2_value if l2_weight > 0 else 0.0

        self.losses = [o.loss for o in objectives] + [l1_value, l2_value]
        tf.scalar_summary('train_l1', l1_value, collections=["summary_train"])
        tf.scalar_summary('train_l2', l2_value, collections=["summary_train"])

        partial_gradients = []  # type: List[Gradients]
        for objective in objectives:
            if objective.gradients is None:
                gradients = self._get_gradients(objective.loss)
                partial_gradients.append(gradients)
            else:
                partial_gradients.append(objective.gradients)
        partial_gradients += [self._get_gradients(l)
                              for l in [l1_cost, l2_cost] if l != 0.]

        gradients = _sum_gradients(partial_gradients)

        if clip_norm is not None:
            gradients = [(tf.clip_by_norm(grad, clip_norm), var)
                         for grad, var in gradients]

        self.all_coders = set.union(*(collect_encoders(obj.decoder)
                                      for obj in objectives))
        self.train_op = self.optimizer.apply_gradients(gradients)

        for grad, var in gradients:
            if grad is not None:
                tf.histogram_summary('gr_' + var.name,
                                     grad, collections=["summary_gradients"])

        self.histogram_summaries = tf.merge_summary(
            tf.get_collection("summary_gradients"))
        self.scalar_summaries = tf.merge_summary(
            tf.get_collection("summary_train"))
        self.image_summaries = tf.merge_summary(
            tf.get_collection("summary_val_plots"))

    def _get_gradients(self, tensor: tf.Tensor) -> Gradients:
        gradient_list = self.optimizer.compute_gradients(tensor)
        return gradient_list

    # pylint: disable=unused-argument
    def get_executable(self, train=False, summaries=True) -> Executable:
        return TrainExecutable(self.all_coders,
                               self.train_op,
                               self.losses,
                               self.scalar_summaries if summaries else None,
                               self.histogram_summaries if summaries else None,
                               self.image_summaries if summaries else None)


def _sum_gradients(gradients_list: List[Gradients]) -> Gradients:
    summed_dict = {}  # type: Dict[tf.Variable, tf.Tensor]
    for gradients in gradients_list:
        for tensor, var in gradients:
            if tensor is not None:
                if not var in summed_dict:
                    summed_dict[var] = tensor
                else:
                    summed_dict[var] += tensor
    return [(tensor, var) for var, tensor in summed_dict.items()]


class TrainExecutable(Executable):

    def __init__(self, all_coders, train_op, losses, scalar_summaries,
                 histogram_summaries, image_summaries):
        self.all_coders = all_coders
        self.train_op = train_op
        self.losses = losses
        self.scalar_summaries = scalar_summaries
        self.histogram_summaries = histogram_summaries
        self.image_summaries = image_summaries

        self.result = None

    def next_to_execute(self) -> NextExecute:
        fetches = {'train_op': self.train_op}
        if self.scalar_summaries is not None:
            fetches['scalar_summaries'] = self.scalar_summaries
            fetches['histogram_summaries'] = self.histogram_summaries
            fetches['image_summaries'] = self.image_summaries
        fetches['losses'] = self.losses

        return self.all_coders, fetches, {}

    def collect_results(self, results: List[Dict]) -> None:
        if self.scalar_summaries is None:
            scalar_summaries = None
            histogram_summaries = None
            image_summaries = None
        else:
            # TODO collect summaries from different sessions
            scalar_summaries = results[0]['scalar_summaries']
            histogram_summaries = results[0]['histogram_summaries']
            image_summaries = results[0]['image_summaries']

        losses_sum = [0. for _ in self.losses]
        for session_result in results:
            for i in range(len(self.losses)):
                # from the end, losses are last ones
                losses_sum[i] += session_result['losses'][i]
        avg_losses = [s / len(results) for s in losses_sum]

        self.result = ExecutionResult(
            [], losses=avg_losses,
            scalar_summaries=scalar_summaries,
            histogram_summaries=histogram_summaries,
            image_summaries=image_summaries)
