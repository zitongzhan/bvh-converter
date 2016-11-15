import numpy as np
from joint import Frame_Joint


class Skeleton(object):
    def __init__(self):
        super(Skeleton, self).__init__()

        self._frame_data = []
        self._joints = []
        self._channels = []

    @property
    def root(self):
        try:
            return self._joints[0]
        except IndexError:
            raise RuntimeError(
                "You must initialize the skeleton with a call to"
                " `_set_hierarchy` before you can get the root node.")

    def _generate_nodes(self, parent, node):
            node.parent = parent
            self._joints.append(node)
            map(lambda kid: self.generate_nodes(node, kid), node.children)

    def _set_hierarchy(self, root_node):
        """Called from `onHierarchy` in the BVH Reader class. Creates a
            depth-first list of Joints in `_joints` and populates `_channels`
            for use with `onFrame`"""
        self._generate_nodes(None, root_node)

        for joint in self._joints:
            self._channels.extend("{}.{}".format(joint.name, joint.channels))
            # May not want to use this...could be more of a pain than it's
            #   worth. The other option is to consume the frame channel data as
            #   we iterate through the joints.

    def get_joint(self, name, joints=None):
        """Gets a reference to a joint object in `self._joints` with name ==
            name if `joints` kwarg is None, else reference to a joint object in
            `joints`. An object is searchable if it has a `name` property

        Positional Arguments:
        name -- name of joint to search for

        Keyword Arguments:
        joints -- list of joints to search through"""
        if joints is None:
            joints = self._joints

        for joint in joints:
            if joint.name == name:
                return joint

        return None

    def get_joint_children(self, name, joints=None):
        """Returns a list of references that are considered children to the
            joint with the given `name`. `joints` kwarg defaults to
            `self._joints`

        Positional Arguments:
        name -- name of parent joint to find children for

        Keyword Arguments:
        joints -- list of joints to search through"""
        ret = []

        if joints is None:
            joints = self._joints

        for joint in joints:
            try:
                parent_name = joint.parent.name
            except AttributeError:
                # This is a Frame Joint with uninitialized parents
                parent_name = joint.parent

            if name == parent_name:
                ret.append(joint)

        return ret

    def _generate_rotation_mtx(self, rotation):
        """Generates 3x3 rotation matrix ordered ZXY.

        Positional Arguments:
        rotation -- (x, y, z) rotation coordinate triple"""
        x, y, z = rotation

        def rotationXMat(angle):
            c, s = np.cos(angle), np.sin(angle)
            return np.array([1, 0, 0,
                             0, c, -s,
                             0, s, c])

        def rotationYMat(angle):
            c, s = np.cos(angle), np.sin(angle)
            return np.array([c, 0, s,
                             0, 1, 0,
                             -s, 0, c])

        def rotationZMat(angle):
            c, s = np.cos(angle), np.sin(angle)
            return np.array([c, -s, 0,
                             s, c, 0,
                             0, 0, 1])

        x_mat = rotationXMat(x)
        y_mat = rotationYMat(y)
        z_mat = rotationZMat(z)

        ret = np.cross(z_mat, x_mat)
        ret = np.cross(ret, y_mat)

        return ret

    def _generate_current_mtx(self, total_offset, rotation):
        """Takes total offset and rotation and creates the current
            transformation matrix that will need to be multiplied with all
            parent matrices.

        Positional Arguments:
        total_offset -- the cumulative offset down to the current joint
        rotation -- the rotation given in the FRAMEDATA as an (x, y, z)
            coordinate triple"""
        ret = np.zeros((4, 4))
        ret[:3, :3] = self._generate_rotation_mtx(rotation)
        ret[3, :3] = total_offset
        ret[3, 3] = 1

        return ret

    def _add_frame(self, values):
        """Called from the BVH Reader class. Internal method to generate and
            save all frame data.

            - This will do the matrix calculations and generate positions on
                the fly.

            - I AM HARDCODING ROTATION ORDER AS ZXY

        Positional Arguments:
        values -- list of values specified by a depth first search of the
            skeleton hierarchy"""

        curr_frame_joints = []
        for joint in self._joints:
            try:
                parent_name = joint.parent.name
            except AttributeError:
                # Root node
                parent_name = None
            frame_joint = Frame_Joint(name=joint.name, position=(0, 0, 0),
                                      transformation_matrix=np.ndarray((4, 4)),
                                      offset=joint.offset,
                                      channels=joint.channels,
                                      parent=parent_name,
                                      children=[])
            curr_frame_joints.append(frame_joint)

        # ^ Populates curr_frame_joints

        for frame_joint in curr_frame_joints:
            frame_joint.parent = self.get_joint(frame_joint.parent,
                                                curr_frame_joints)
            frame_joint.children = \
                self.get_joint_children(frame_joint.name, curr_frame_joints)

        # ^ assigns parents and children to curr_frame_joints

        # TODO: Position math

        for frame_joint in curr_frame_joints:
            chan_vals = values[:len(frame_joint.channels)]
            values = values[len(frame_joint.channels):]

            x_pos, y_pos, z_pos = 0, 0, 0
            x_rot, y_rot, z_rot = 0, 0, 0
            for i, chan in enumerate(frame_joint.channels):
                if 'position' in chan.lower():
                    if 'x' in chan.lower():
                        x_pos = chan_vals[i]
                    elif 'y' in chan.lower():
                        y_pos = chan_vals[i]
                    else:
                        z_pos = chan_vals[i]
                else:
                    if 'x' in chan.lower():
                        x_rot = chan_vals[i]
                    elif 'y' in chan.lower():
                        y_rot = chan_vals[i]
                    else:
                        z_rot = chan_vals[i]

                position = np.ndarray([x_pos, y_pos, z_pos])
                rotation = np.ndarray([x_rot, y_rot, z_rot])

                frame_joint.position = position

                curr_matrix = self._generate_current_mtx(
                    frame_joint.total_offset, rotation)

                full_curr_mtx = np.cross(
                    frame_joint.parent.transformation_matrix, curr_matrix)

                frame_joint.transformation_matrix = full_curr_mtx

                if len(frame_joint.channels) == 3:
                    # not root
                    frame_joint.position = np.cross(
                        full_curr_mtx, np.ndarray([0, 0, 0, 1]).transpose())

        self._frame_data.append(curr_frame_joints)
        # Jesus help me

    def frames(self, n=None):
        """Returns a list of frames, first item in list will be a header

        Positional Arguments
        n -- if not None, returns specified frame (with header)"""
        if n is None:
            return self._frame_data
        else:
            return self._frame_data[n]
