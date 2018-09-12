"""
Original work Copyright 2017 Carlos Scheidegger, Sorelle Friedler, Suresh Venkatasubramanian
Modified work Copyright 2018 IBM Corporation

Licensed under the Apache License, Version 2.0 (the "License"); you may not
use this file except in compliance with the License. You may obtain a copy of 
the License at http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed
under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR 
CONDITIONS OF ANY KIND, either express or implied. See the License for the 
specific language governing permissions and limitations under the License. 
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

"""The code for PrejudiceRemover is a modification of, and based on, the
implementation of Kamishima Algorithm by fairness-comparison.

See: https://github.com/algofairness/fairness-comparison/tree/master/fairness/algorithms/kamishima

Notes from fairness-comparison's KamishimaAlgorithm.py on changes made to original Kamishima code.

    - The original code depends on python2's commands library. We hacked
    it to hve python3 support by adding a minimal commands.py module with
    a getoutput function.

    ## Getting train_pr to work

    It takes as input a space-separated file.

    Its value imputation is quite naive (replacing nans with column
    means), so we will impute values ourselves ahead of time if necessary.

    The documentation describes 'ns' as the number of sensitive features,
    but the code hardcodes ns=1, and things only seem to make sense if
    'ns' is, instead, the column _index_ for the sensitive feature,
    _counting from the end, and excluding the target class_. In addition,
    it seems that if the sensitive feature is not the last column of the
    data, the code will drop all features after that column.

    tl;dr:

    - the last column of the input should be the target class (as integer values),
    - the code only appears to support one sensitive feature at a time,
    - the second-to-last column of the input should be the sensitive feature (as integer values)
    - fill missing values ahead of time in order to avoid imputation.

    If you do this, train_pr.py:148-149 will take the last column to be y
    (the target classes to predict), then pr.py:264 will take the
    second-to-last column as the sensitive attribute, and pr.py:265-268
    will take the remaining columns as non-sensitive.
    
    The code in kamfadm-2012ecmlpkdd/ is the (fairness-comparison) modified version of the original ECML paper code
    
    See: changes-to-downloaded-code.diff and KamishimaAlgorithm.py for more details
"""

import numpy as np
import pandas as pd
import tempfile
import os
import subprocess

from aif360.algorithms import Transformer


class PrejudiceRemover(Transformer):
    """
     Prejudice remover is an in-processing technique that adds a discrimination-aware
     regularization term to the learning objective [6]_.
     
     References:
         .. [6] T. Kamishima, S. Akaho, H. Asoh, and J. Sakuma, "Fairness-Aware Classifier with Prejudice Remover
            Regularizer," Joint European Conference on Machine Learning and Knowledge Discovery in Databases, 2012.
    
    """

    def __init__(self, eta=1.0, sensitive_attr="", class_attr=""):
        """
        Args:
            eta (double, optional): fairness penalty parameter
            sensitive_attr (str, optional): name of protected attribute
            class_attr (str, optional): label name
        """
        super(PrejudiceRemover, self).__init__(eta=eta,
            sensitive_attr=sensitive_attr, class_attr=class_attr)
        self.eta = eta
        self.sensitive_attr = sensitive_attr
        self.class_attr = class_attr

    def fit(self, dataset):
        data = np.column_stack([dataset.features, dataset.labels])
        columns = dataset.feature_names + dataset.label_names
        train_df = pd.DataFrame(data=data, columns=columns)

        # privileged_vals = [1 for x in dataset.protected_attribute_names]
        all_sensitive_attributes = dataset.protected_attribute_names

        if not self.sensitive_attr:
            self.sensitive_attr = all_sensitive_attributes[0]
        # else:
        #     single_sensitive_value = self.sensitive_attr

        if not self.class_attr:
            self.class_attr = dataset.label_names[0]
        # else:
        #     class_attr = self.class_attr

        # positive_val = dataset.privileged_protected_attributes[0][0] #TODO same as above..specify class to use

        # model_name = self._runTrain(train_df, class_attr, positive_val, all_sensitive_attributes,
        #     single_sensitive_value, privileged_vals)
        model_name = self._runTrain(train_df, self.class_attr, None,
            all_sensitive_attributes, self.sensitive_attr, None)

        self.model_name = model_name
        return self

    def predict(self, dataset):
        data = np.column_stack([dataset.features, dataset.labels])
        columns = dataset.feature_names + dataset.label_names
        test_df = pd.DataFrame(data=data, columns=columns)

        # privileged_vals = [1 for x in dataset.protected_attribute_names]
        all_sensitive_attributes = dataset.protected_attribute_names
        # single_sensitive_value = all_sensitive_attributes[0] #TODO specify WHICH sensitive value to use
        # class_attr = dataset.label_names[0] ##TO DO one should specify WHICH label to use
        # positive_val = dataset.privileged_protected_attributes[0][0] #TODO same as above..specify class to use

        predictions, scores = self._runTest(test_df, self.class_attr, None,
            all_sensitive_attributes, self.sensitive_attr, None)

        pred_dataset = dataset.copy()
        pred_dataset.labels = predictions
        pred_dataset.scores = scores

        return pred_dataset

    def _runTrain(self, train_df, class_attr, positive_class_val, sensitive_attrs,
                  single_sensitive, privileged_vals):
        def create_file_in_kamishima_format(df):
            s = df[single_sensitive]

            x = []
            for col in df:
                if col == class_attr:
                    continue
                if col in sensitive_attrs:
                    continue
                x.append(np.array(df[col].values, dtype=np.float64))

            x.append(np.array(s, dtype=np.float64))
            x.append(np.array(df[class_attr], dtype=np.float64))

            result = np.array(x).T
            fd, name = tempfile.mkstemp()
            os.close(fd)
            np.savetxt(name, result)
            return name

        fd, model_name = tempfile.mkstemp()
        os.close(fd)
        train_name = create_file_in_kamishima_format(train_df)
        eta_val = self.eta
        #ADDED FOLLOWING LINE to get absolute path of this file, i.e. KamishimaAlgorithm.py
        k_path = os.path.dirname(os.path.abspath(__file__))
        #changed paths in the calls below to (a) specify path of train_pr,predict_lr RELATIVE to this file, and (b) compute & use absolute path, and (c) replace python3 with python
        subprocess.run(['python', os.path.join(k_path, 'kamfadm-2012ecmlpkdd', 'train_pr.py'),
                        '-e', str(eta_val),
                        '-i', train_name,
                        '-o', model_name,
                        '--quiet'])
        os.unlink(train_name)
        #os.unlink(model_name)

        ## TODO Right now, it just returns the file created. Need to change to read the file and return the model
        return model_name

    def _runTest(self, test_df, class_attr, positive_class_val, sensitive_attrs,
                 single_sensitive, privileged_vals):
        def create_file_in_kamishima_format(df):
            s = df[single_sensitive]

            x = []
            for col in df:
                if col == class_attr:
                    continue
                if col in sensitive_attrs:
                    continue
                x.append(np.array(df[col].values, dtype=np.float64))

            x.append(np.array(s, dtype=np.float64))
            x.append(np.array(df[class_attr], dtype=np.float64))

            result = np.array(x).T
            fd, name = tempfile.mkstemp()
            os.close(fd)
            np.savetxt(name, result)
            return name

        #fd, model_name = tempfile.mkstemp()
        #os.close(fd)
        fd, output_name = tempfile.mkstemp()
        os.close(fd)

        test_name = create_file_in_kamishima_format(test_df)

        #ADDED FOLLOWING LINE to get absolute path of this file, i.e. KamishimaAlgorithm.py
        k_path = os.path.dirname(os.path.abspath(__file__))
        #changed paths in the calls below to (a) specify path of train_pr,predict_lr RELATIVE to this file, and (b) compute & use absolute path, and (c) replace python3 with python
        subprocess.run(['python', os.path.join(k_path, 'kamfadm-2012ecmlpkdd', 'predict_lr.py'),
                        '-i', test_name,
                        '-m', self.model_name,
                        '-o', output_name,
                        '--quiet'])

        #os.unlink(model_name)
        os.unlink(test_name)

        m = np.loadtxt(output_name)
        os.unlink(output_name)

        """
        Columns of Outputs: (as per Kamishima implementation...predict_lr.py)

        1. true sample class number
        2. predicted class number
        3. sensitive feature
        4. class 0 probability
        5. class 1 probability
        """
        predictions = m[:, 1]
        prediction_probs = m[:, 3:5]

        return predictions, prediction_probs